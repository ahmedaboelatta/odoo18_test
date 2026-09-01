import logging

from odoo import fields, models


_logger = logging.getLogger(__name__)


class TechrarWebhookEvent(models.Model):
    _name = 'techrar.webhook.event'
    _description = 'Techrar Webhook Processing Queue'
    _order = 'id'

    config_id = fields.Many2one('techrar.config', required=True, ondelete='cascade')
    techrar_order_id = fields.Char(required=True, index=True)
    payload = fields.Json(required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], required=True, default='pending', index=True)
    attempts = fields.Integer(default=0)
    last_error = fields.Text()
    processed_at = fields.Datetime()

    _sql_constraints = [
        (
            'techrar_webhook_config_order_unique',
            'unique(config_id, techrar_order_id)',
            'This Techrar webhook order is already queued.',
        ),
    ]

    def _process_event(self):
        self.ensure_one()
        today = fields.Date.today()
        wizard = self.env['techrar.sync.wizard'].create({
            'config_id': self.config_id.id,
            'from_date': today,
            'to_date': today,
            'run_source': 'webhook',
        })
        return wizard._process_webhook_payload(self.payload, self.config_id)

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

    def _cron_process_pending(self):
        events = self.search(self._retry_domain(), limit=20)
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
                        continue
                    event.write({
                        'state': 'done',
                        'processed_at': fields.Datetime.now(),
                    })
            except Exception as error:
                _logger.exception(
                    'Failed to process queued Techrar webhook order %s.',
                    event.techrar_order_id,
                )
                event._mark_failed(error, attempts)
        remaining = self.search_count(self._retry_domain())
        return remaining
