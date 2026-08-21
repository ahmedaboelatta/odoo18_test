import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BirdBulkSend(models.Model):
    _name = 'bird.bulk.send'
    _description = 'Bird WhatsApp Bulk Send'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New Bulk Send'), tracking=True, copy=False)
    organization_id = fields.Many2one('bird.organization', required=True, ondelete='restrict', index=True)
    workspace_id = fields.Many2one('bird.workspace', required=True, ondelete='restrict', index=True)
    channel_id = fields.Many2one('bird.channel', required=True, ondelete='restrict', index=True)
    template_id = fields.Many2one('bird.template', required=True, ondelete='restrict', index=True)
    locale = fields.Selection([('en', 'English'), ('ar', 'Arabic')], default='en', required=True)
    reference = fields.Char()
    parameter_json = fields.Text(string='Template Parameters JSON', readonly=True)

    state = fields.Selection([
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('partial', 'Completed with Errors'),
        ('cancelled', 'Cancelled'),
    ], default='queued', required=True, tracking=True, index=True)

    line_ids = fields.One2many('bird.bulk.send.line', 'batch_id', string='Recipients')
    total_count = fields.Integer(compute='_compute_counts', store=True)
    pending_count = fields.Integer(compute='_compute_counts', store=True)
    submitted_count = fields.Integer(compute='_compute_counts', store=True)
    sent_count = fields.Integer(compute='_compute_counts', store=True)
    delivered_count = fields.Integer(compute='_compute_counts', store=True)
    read_count = fields.Integer(compute='_compute_counts', store=True)
    failed_count = fields.Integer(compute='_compute_counts', store=True)
    ready_count = fields.Integer(compute='_compute_counts', store=True)
    invalid_count = fields.Integer(compute='_compute_counts', store=True)
    sync_failed_count = fields.Integer(compute='_compute_counts', store=True)
    progress = fields.Float(compute='_compute_counts', store=True)

    batch_size = fields.Integer(
        string='Messages per Run', default=10, required=True,
        help='Maximum recipients processed by each queue run. The scheduler runs once per minute.'
    )
    max_retries = fields.Integer(default=2, required=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    last_run_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)

    @api.depends('line_ids.state', 'line_ids.preflight_state')
    def _compute_counts(self):
        for batch in self:
            states = batch.line_ids.mapped('state')
            batch.total_count = len(states)
            batch.pending_count = sum(1 for s in states if s in ('pending', 'retry', 'processing'))
            batch.submitted_count = sum(1 for s in states if s in ('submitted', 'sent', 'delivered', 'read'))
            # Bird HTTP 2xx/accepted means the send job was successfully submitted.
            # Count submitted as sent for bulk execution metrics; delivery/read remain separate tracking metrics.
            batch.sent_count = sum(1 for s in states if s in ('submitted', 'sent', 'delivered', 'read'))
            batch.delivered_count = sum(1 for s in states if s in ('delivered', 'read'))
            batch.read_count = sum(1 for s in states if s == 'read')
            batch.failed_count = sum(1 for s in states if s == 'failed')
            batch.ready_count = sum(1 for line in batch.line_ids if line.preflight_state == 'ready')
            batch.invalid_count = sum(1 for line in batch.line_ids if line.preflight_state == 'invalid')
            batch.sync_failed_count = sum(1 for line in batch.line_ids if line.preflight_state == 'sync_failed')
            # Bulk progress measures queue execution, not downstream WhatsApp delivery.
            # A submitted message has completed the bulk sender's job; webhook updates can later
            # promote it to delivered/read without keeping the batch artificially Running.
            finished = batch.submitted_count + batch.failed_count
            batch.progress = (finished * 100.0 / batch.total_count) if batch.total_count else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == _('New Bulk Send'):
                vals['name'] = seq.next_by_code('bird.bulk.send') or _('Bird Bulk Send')
        return super().create(vals_list)

    def action_cancel(self):
        for batch in self.filtered(lambda b: b.state in ('queued', 'running')):
            batch.write({'state': 'cancelled', 'finished_at': fields.Datetime.now()})
            batch.line_ids.filtered(lambda l: l.state in ('pending', 'retry')).write({'state': 'cancelled'})
        return True

    def action_process_now(self):
        self.ensure_one()
        if self.state == 'cancelled':
            raise UserError(_('A cancelled batch cannot be processed.'))
        self._process_queue_once()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk Send'),
                'message': _('Queue run completed. %s submitted, %s delivered, %s failed, %s pending.') % (
                    self.submitted_count, self.delivered_count, self.failed_count, self.pending_count),
                'type': 'success' if not self.failed_count else 'warning',
                'sticky': False,
            },
        }

    def action_retry_failed(self):
        for batch in self:
            lines = batch.line_ids.filtered(lambda l: l.state == 'failed' and l.auto_retry_allowed)
            lines.write({'state': 'retry', 'error_message': False})
            if lines:
                batch.write({'state': 'queued', 'finished_at': False, 'last_error': False})
        return True

    def action_open_messages(self):
        self.ensure_one()
        action = self.env.ref('bird_connector.action_bird_message_log').read()[0]
        action['domain'] = [('bulk_send_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    def _preflight_line(self, line):
        """Validate a recipient and ensure it has a real Bird Contact ID."""
        contact = line.contact_id.sudo()
        phone = contact._format_phone_e164(contact.whatsapp_number, organization=contact.organization_id)
        digits = ''.join(ch for ch in (phone or '') if ch.isdigit())
        if not phone or not phone.startswith('+') or not (8 <= len(digits) <= 15):
            line.write({
                'preflight_state': 'invalid',
                'preflight_error': _('Invalid WhatsApp number: %s') % (contact.whatsapp_number or ''),
                'state': 'failed',
                'error_message': _('Invalid WhatsApp number.'),
                'auto_retry_allowed': False,
            })
            return False
        try:
            if contact.whatsapp_number != phone:
                contact.with_context(skip_bird_contact_sync=True).write({'whatsapp_number': phone})
            if not contact.bird_contact_id or contact.bird_sync_status != 'synced':
                contact._sync_bird_contact_identity(raise_on_error=True)
            if not contact.bird_contact_id:
                raise UserError(_('Bird Contact ID was not returned.'))
            line.write({
                'preflight_state': 'ready',
                'preflight_error': False,
                'preflight_at': fields.Datetime.now(),
            })
            return True
        except Exception as exc:
            line.write({
                'preflight_state': 'sync_failed',
                'preflight_error': str(exc),
                'state': 'failed',
                'error_message': str(exc),
                'auto_retry_allowed': False,
            })
            return False

    def _process_queue_once(self):
        engine = self.env['bird.message.engine']
        for batch in self:
            if batch.state not in ('queued', 'running'):
                continue
            if not batch.started_at:
                batch.started_at = fields.Datetime.now()
            batch.state = 'running'
            batch.last_run_at = fields.Datetime.now()
            lines = batch.line_ids.filtered(lambda l: l.state in ('pending', 'retry')).sorted('id')[:max(batch.batch_size, 1)]
            if not lines:
                batch._finish_if_complete()
                continue

            import json
            try:
                parameters = json.loads(batch.parameter_json or '[]')
            except Exception:
                parameters = []

            for line in lines:
                line.write({'state': 'processing', 'last_attempt_at': fields.Datetime.now(), 'attempt_count': line.attempt_count + 1})
                try:
                    if line.preflight_state != 'ready' and not batch._preflight_line(line):
                        continue
                    log = engine.send_whatsapp_template(
                        channel=batch.channel_id,
                        receiver=line.contact_id.whatsapp_number,
                        template=batch.template_id,
                        parameters=parameters,
                        locale=batch.locale,
                        reference=batch.reference,
                    )
                    log.write({'bulk_send_id': batch.id, 'bulk_send_line_id': line.id})
                    if log.status == 'failed':
                        raise UserError(log.error_message or _('Bird reported the message as failed.'))
                    line.write({'state': 'submitted', 'message_log_id': log.id, 'submitted_at': fields.Datetime.now(), 'error_message': False, 'failure_code': False, 'failure_reason': False})
                except Exception as exc:
                    _logger.exception('Bird bulk send line failed: batch=%s line=%s', batch.id, line.id)
                    can_retry = line.attempt_count <= batch.max_retries
                    line.write({
                        'state': 'retry' if can_retry else 'failed',
                        'error_message': str(exc),
                    })
                    batch.last_error = str(exc)
            batch._finish_if_complete()
        return True

    def _finish_if_complete(self):
        for batch in self:
            remaining = batch.line_ids.filtered(lambda l: l.state in ('pending', 'retry', 'processing'))
            if remaining:
                batch.state = 'running'
                continue
            batch.write({
                'state': 'partial' if batch.failed_count else 'done',
                'finished_at': fields.Datetime.now(),
            })

    @api.model
    def _cron_process_bulk_sends(self):
        batches = self.search([('state', 'in', ('queued', 'running'))], order='create_date asc, id asc', limit=5)
        batches._process_queue_once()
        return True


class BirdBulkSendLine(models.Model):
    _name = 'bird.bulk.send.line'
    _description = 'Bird WhatsApp Bulk Send Recipient'
    _order = 'id'

    batch_id = fields.Many2one('bird.bulk.send', required=True, ondelete='cascade', index=True)
    contact_id = fields.Many2one('bird.contact', required=True, ondelete='restrict', index=True)
    phone_number = fields.Char(related='contact_id.whatsapp_number', store=True, readonly=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('retry', 'Retry'),
        ('submitted', 'Submitted'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='pending', required=True, index=True)
    preflight_state = fields.Selection([
        ('pending', 'Pending Check'),
        ('ready', 'Ready'),
        ('invalid', 'Invalid Number'),
        ('sync_failed', 'Sync Failed'),
    ], string='Pre-Sync', default='pending', required=True, readonly=True, index=True)
    preflight_at = fields.Datetime(string='Pre-Sync At', readonly=True)
    preflight_error = fields.Text(string='Pre-Sync Error', readonly=True)
    attempt_count = fields.Integer(default=0, readonly=True)
    last_attempt_at = fields.Datetime(readonly=True)
    submitted_at = fields.Datetime(readonly=True)
    sent_at = fields.Datetime(readonly=True)
    delivered_at = fields.Datetime(readonly=True)
    read_at = fields.Datetime(readonly=True)
    failure_code = fields.Char(readonly=True)
    failure_reason = fields.Text(readonly=True)
    auto_retry_allowed = fields.Boolean(default=True, readonly=True)
    message_log_id = fields.Many2one('bird.message.log', readonly=True, ondelete='set null')
    error_message = fields.Text(readonly=True)
