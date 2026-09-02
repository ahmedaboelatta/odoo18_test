import json
import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError


_logger = logging.getLogger(__name__)


class TechrarWebhookEvent(models.Model):
    _name = 'techrar.webhook.event'
    _description = 'Techrar Webhook Processing Queue'
    _order = 'create_date desc, id desc'

    config_id = fields.Many2one('techrar.config', required=True, ondelete='cascade')
    techrar_order_id = fields.Char(required=True, index=True)
    payload = fields.Json(required=True)
    payload_text = fields.Text(compute='_compute_payload_text')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], required=True, default='pending', index=True)
    attempts = fields.Integer(default=0)
    last_error = fields.Text()
    processed_at = fields.Datetime()

    @api.depends('payload')
    def _compute_payload_text(self):
        for event in self:
            event.payload_text = json.dumps(
                event.payload or {}, ensure_ascii=False, indent=2,
            )

    _sql_constraints = [
        (
            'techrar_webhook_config_order_unique',
            'unique(config_id, techrar_order_id)',
            'This Techrar webhook order is already queued.',
        ),
    ]

    @api.model
    def web_search_read(
        self, domain, specification, offset=0, limit=None, order=None,
        count_limit=None,
    ):
        # This model is an operational queue: always show its newest event
        # first.  Odoo's web client may otherwise restore a stale user sort
        # and override both _order and the list view's default_order.
        order = 'create_date desc, id desc'
        return super().web_search_read(
            domain,
            specification,
            offset=offset,
            limit=limit,
            order=order,
            count_limit=count_limit,
        )

    def _process_event(self):
        self.ensure_one()
        today = fields.Date.today()
        wizard = self.env['techrar.sync.wizard'].create({
            'config_id': self.config_id.id,
            'from_date': today,
            'to_date': today,
            'run_source': 'webhook',
        })
        return wizard.with_context(
            # Techrar can emit the event before its public API exposes the
            # order.  Preserve four enrichment retries, then import the safe
            # financial payload on the fifth instead of losing the order.
            techrar_allow_partial=self.attempts >= 5,
        )._process_webhook_payload(self.payload, self.config_id)

    @staticmethod
    def _retry_domain():
        return [('state', 'in', ('pending', 'failed')), ('attempts', '<', 5)]

    def _mark_failed(self, error, attempts):
        self.write({
            'state': 'failed',
            'attempts': attempts,
            'last_error': str(error)[:2000],
        })
        self.env['techrar.sync.log'].create({
            'techrar_order_id': self.techrar_order_id,
            'status': 'failed',
            'message': str(error)[:2000],
            'run_source': 'webhook',
        })

    def _recover_stale_processing(self):
        """Put events abandoned by an interrupted worker back in the queue."""
        stale_before = fields.Datetime.subtract(fields.Datetime.now(), minutes=10)
        stale = self.search([
            ('state', '=', 'processing'),
            ('write_date', '<', stale_before),
        ])
        if stale:
            stale.write({
                'state': 'pending',
                'last_error': 'Previous processing was interrupted; queued automatically.',
            })
        return len(stale)

    def _process_events(self, events):
        processed = failed = deferred = 0
        for event in events:
            attempts = event.attempts + 1
            try:
                with self.env.cr.savepoint():
                    event.write({
                        'state': 'processing',
                        'attempts': attempts,
                        'last_error': False,
                    })
                    result, unused_order_id = event._process_event()
                    del unused_order_id
                    if result == 'deferred':
                        # Lock contention is normal when scheduled sync owns
                        # the same order; it must not consume a retry attempt.
                        event.write({
                            'state': 'pending',
                            'attempts': attempts - 1,
                        })
                        deferred += 1
                        continue
                event.write({
                    'state': 'done',
                    'processed_at': fields.Datetime.now(),
                })
                processed += 1
            except Exception as error:
                _logger.exception(
                    'Failed to process queued Techrar webhook order %s.',
                    event.techrar_order_id,
                )
                event._mark_failed(error, attempts)
                failed += 1
        return processed, failed, deferred

    @api.model
    def _cron_process_pending(self):
        self._recover_stale_processing()
        events = self.search(self._retry_domain(), limit=20)
        self._process_events(events)
        remaining = self.search_count(self._retry_domain())
        return remaining

    @api.model
    def action_process_pending_now(self):
        """Give managers a synchronous recovery path when cron is unavailable."""
        if not self.env.user.has_group(
            'techrar_connector.module_techrar_connector_manager'
        ):
            raise AccessError('Only a Techrar Connector Manager can process the queue.')
        recovered = self._recover_stale_processing()
        events = self.search(self._retry_domain(), limit=50)
        processed, failed, deferred = self._process_events(events)
        remaining = self.search_count([
            ('state', 'in', ('pending', 'processing', 'failed')),
        ])
        message = (
            f'Processed: {processed}; Failed: {failed}; Deferred: {deferred}; '
            f'Remaining: {remaining}.'
        )
        if recovered:
            message += f' Recovered interrupted events: {recovered}.'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Techrar Webhook Queue',
                'message': message,
                'type': 'success' if not failed and not remaining else 'warning',
                'sticky': bool(failed or remaining),
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_retry_now(self):
        if not self.env.user.has_group(
            'techrar_connector.module_techrar_connector_manager'
        ):
            raise AccessError('Only a Techrar Connector Manager can retry events.')
        retryable = self.filtered(lambda event: event.state != 'done')
        retryable.write({
            'state': 'pending',
            'attempts': 0,
            'last_error': False,
            'processed_at': False,
        })
        processed, failed, deferred = self._process_events(retryable[:50])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Webhook Retry',
                'message': (
                    f'Processed: {processed}; Failed: {failed}; Deferred: {deferred}.'
                ),
                'type': 'success' if not failed else 'warning',
                'sticky': bool(failed),
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }
