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
        ('paused', 'Paused'),
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
    progress = fields.Float(string='Processing Progress (%)', compute='_compute_counts', store=True)
    submission_rate = fields.Float(string='Submission Rate (%)', compute='_compute_counts', store=True, digits=(16, 2))
    delivery_rate = fields.Float(string='Delivery Rate (%)', compute='_compute_counts', store=True, digits=(16, 2))
    failure_rate = fields.Float(string='Failure Rate (%)', compute='_compute_counts', store=True, digits=(16, 2))
    retryable_failed_count = fields.Integer(string='Retryable Failed', compute='_compute_counts', store=True)
    non_retryable_failed_count = fields.Integer(string='Non-Retryable Failed', compute='_compute_counts', store=True)

    scheduled_at = fields.Datetime(
        string='Schedule At',
        help='Leave empty to start as soon as the queue scheduler picks up the campaign.'
    )
    next_run_at = fields.Datetime(string='Next Batch At', readonly=True, index=True)
    batch_size = fields.Integer(
        string='Batch Size', default=10, required=True,
        help='Maximum recipients processed in each campaign batch.'
    )
    batch_interval_minutes = fields.Integer(
        string='Batch Interval (Minutes)', default=1, required=True,
        help='Minimum waiting time between two campaign batches. The scheduler itself runs once per minute.'
    )
    max_retries = fields.Integer(default=2, required=True)
    paused_at = fields.Datetime(readonly=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    last_run_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)


    @api.model
    def campaign_dashboard_data(self, period='30'):
        """Portable dashboard data; no database/domain/server assumptions."""
        from datetime import timedelta
        domain = []
        if period != 'all':
            try:
                days = max(1, int(period))
            except (TypeError, ValueError):
                days = 30
            domain = [('create_date', '>=', fields.Datetime.now() - timedelta(days=days))]

        batches = self.search(domain)
        lines = batches.mapped('line_ids')
        total = len(lines)
        submitted = len(lines.filtered(lambda l: l.state in ('submitted', 'sent', 'delivered', 'read')))
        delivered = len(lines.filtered(lambda l: l.state in ('delivered', 'read')))
        failed = len(lines.filtered(lambda l: l.state == 'failed'))
        pending = len(lines.filtered(lambda l: l.state in ('pending', 'retry', 'processing')))
        delivery_pct = round((delivered * 100.0 / total), 1) if total else 0.0
        failure_pct = round((failed * 100.0 / total), 1) if total else 0.0

        cards = [
            {'key':'campaigns','label':_('Campaigns'),'value':len(batches),'note':_('in selected period'),'domain':[]},
            {'key':'recipients','label':_('Recipients'),'value':total,'note':_('total audience'),'domain':[]},
            {'key':'submitted','label':_('Submitted'),'value':submitted,'note':_('accepted for sending'),'domain':[('state','in',('submitted','sent','delivered','read'))]},
            {'key':'delivered','label':_('Delivered'),'value':delivered,'note':_('%s%% of total audience') % delivery_pct,'domain':[('state','in',('delivered','read'))]},
            {'key':'failed','label':_('Failed'),'value':failed,'note':_('%s%% failure rate') % failure_pct,'domain':[('state','=','failed')]},
            {'key':'pending','label':_('Pending'),'value':pending,'note':_('still processing'),'domain':[('state','in',('pending','retry','processing'))]},
        ]
        denom = total or 1
        funnel = [
            {'label':_('Recipients'), 'value':total, 'percent':100 if total else 0},
            {'label':_('Submitted'), 'value':submitted, 'percent':round(submitted*100.0/denom,1)},
            {'label':_('Delivered'), 'value':delivered, 'percent':round(delivered*100.0/denom,1)},
            {'label':_('Failed'), 'value':failed, 'percent':round(failed*100.0/denom,1)},
        ]
        labels = dict(self._fields['state'].selection)
        states = [{'key':k, 'label':labels.get(k,k), 'count':len(batches.filtered(lambda b, key=k: b.state == key))} for k in labels]

        failure_map = {}
        for line in lines.filtered(lambda l: l.state == 'failed'):
            key = (line.failure_code or '', line.failure_reason or '')
            failure_map[key] = failure_map.get(key, 0) + 1
        failures = []
        for (code, reason), count in sorted(failure_map.items(), key=lambda x: x[1], reverse=True)[:8]:
            d=[('state','=','failed')]
            if code: d.append(('failure_code','=',code))
            if reason: d.append(('failure_reason','=',reason))
            failures.append({'code':code,'reason':reason,'count':count,'domain':d})

        channel_map = {}
        for line in lines:
            ch = line.channel_id
            if not ch: continue
            row = channel_map.setdefault(ch.id, {'id':ch.id,'name':ch.display_name,'total':0,'delivered':0})
            row['total'] += 1
            if line.state in ('delivered','read'): row['delivered'] += 1
        channels = sorted(channel_map.values(), key=lambda x: x['total'], reverse=True)[:8]
        return {'cards':cards,'funnel':funnel,'states':states,'failures':failures,'channels':channels}

    @api.depends('line_ids.state', 'line_ids.preflight_state', 'line_ids.is_read', 'line_ids.auto_retry_allowed')
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
            batch.read_count = sum(1 for line in batch.line_ids if line.is_read or line.state == 'read')
            batch.failed_count = sum(1 for s in states if s == 'failed')
            batch.ready_count = sum(1 for line in batch.line_ids if line.preflight_state == 'ready')
            batch.invalid_count = sum(1 for line in batch.line_ids if line.preflight_state == 'invalid')
            batch.sync_failed_count = sum(1 for line in batch.line_ids if line.preflight_state == 'sync_failed')
            batch.retryable_failed_count = sum(1 for line in batch.line_ids if line.state == 'failed' and line.auto_retry_allowed)
            batch.non_retryable_failed_count = sum(1 for line in batch.line_ids if line.state == 'failed' and not line.auto_retry_allowed)
            # Store rates as real percentage points (0..100).  This intentionally avoids
            # Odoo's percentage widget, which multiplies ratio values again when rendering.
            # All campaign rates use Total Audience as the denominator so the list, form and
            # dashboard tell the same story: submitted + delivered + failed are audience KPIs.
            batch.submission_rate = (batch.submitted_count * 100.0 / batch.total_count) if batch.total_count else 0.0
            batch.delivery_rate = (batch.delivered_count * 100.0 / batch.total_count) if batch.total_count else 0.0
            batch.failure_rate = (batch.failed_count * 100.0 / batch.total_count) if batch.total_count else 0.0
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
        records = super().create(vals_list)
        now = fields.Datetime.now()
        for batch in records:
            if not batch.next_run_at:
                batch.next_run_at = batch.scheduled_at or now
        return records

    def action_pause(self):
        for batch in self.filtered(lambda b: b.state in ('queued', 'running')):
            batch.write({'state': 'paused', 'paused_at': fields.Datetime.now()})
        return True

    def action_resume(self):
        now = fields.Datetime.now()
        for batch in self.filtered(lambda b: b.state == 'paused'):
            next_at = batch.scheduled_at if batch.scheduled_at and batch.scheduled_at > now else now
            batch.write({'state': 'queued', 'paused_at': False, 'next_run_at': next_at, 'finished_at': False})
        return True

    def action_cancel(self):
        for batch in self.filtered(lambda b: b.state in ('queued', 'running', 'paused')):
            batch.write({'state': 'cancelled', 'finished_at': fields.Datetime.now()})
            batch.line_ids.filtered(lambda l: l.state in ('pending', 'retry', 'processing')).write({'state': 'cancelled'})
        return True

    def action_process_now(self):
        self.ensure_one()
        if self.state == 'cancelled':
            raise UserError(_('A cancelled batch cannot be processed.'))
        self.with_context(force_bulk_process=True)._process_queue_once()
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
                batch.write({'state': 'queued', 'finished_at': False, 'last_error': False, 'next_run_at': fields.Datetime.now()})
        return True

    def action_open_messages(self):
        self.ensure_one()
        action = self.env.ref('bird_connector.action_bird_message_log').read()[0]
        action['domain'] = [('bulk_send_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    def _action_open_recipient_lines(self, title, domain):
        self.ensure_one()
        action = self.env.ref('bird_connector.action_bird_bulk_send_recipient_analytics').read()[0]
        action['name'] = title
        action['domain'] = [('batch_id', '=', self.id)] + list(domain)
        action['context'] = {'create': False, 'default_batch_id': self.id}
        return action

    def action_open_all_recipients(self):
        return self._action_open_recipient_lines(_('Campaign Recipients'), [])

    def action_open_delivered_recipients(self):
        return self._action_open_recipient_lines(_('Delivered Recipients'), [('state', '=', 'delivered')])

    def action_open_failed_recipients(self):
        return self._action_open_recipient_lines(_('Failed Recipients'), [('state', '=', 'failed')])

    def action_open_retryable_failed(self):
        return self._action_open_recipient_lines(
            _('Retryable Failed Recipients'), [('state', '=', 'failed'), ('auto_retry_allowed', '=', True)]
        )

    def action_open_failure_analysis(self):
        self.ensure_one()
        action = self.env.ref('bird_connector.action_bird_bulk_send_recipient_analytics').read()[0]
        action['name'] = _('Failure Analysis - %s') % self.display_name
        action['domain'] = [('batch_id', '=', self.id), ('state', '=', 'failed')]
        action['view_mode'] = 'pivot,graph,list'
        action['context'] = {
            'create': False,
            'search_default_group_failure_code': 1,
        }
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
            now = fields.Datetime.now()
            force = bool(self.env.context.get('force_bulk_process'))
            if not force:
                if batch.scheduled_at and batch.scheduled_at > now:
                    continue
                if batch.next_run_at and batch.next_run_at > now:
                    continue
            if not batch.started_at:
                batch.started_at = now
            batch.state = 'running'
            batch.last_run_at = now
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
            if batch.state == 'running':
                batch.next_run_at = fields.Datetime.add(
                    fields.Datetime.now(), minutes=max(batch.batch_interval_minutes or 0, 0)
                )
        return True

    def _finish_if_complete(self):
        for batch in self:
            remaining = batch.line_ids.filtered(lambda l: l.state in ('pending', 'retry', 'processing'))
            if remaining:
                if batch.state != 'paused':
                    batch.state = 'running'
                continue
            vals = {
                'state': 'partial' if batch.failed_count else 'done',
                'next_run_at': False,
            }
            if not batch.finished_at:
                vals['finished_at'] = fields.Datetime.now()
            batch.write(vals)

    @api.model
    def _cron_process_bulk_sends(self):
        batches = self.search([('state', 'in', ('queued', 'running'))], order='create_date asc, id asc', limit=5)
        batches._process_queue_once()
        return True


    @api.constrains('batch_size', 'batch_interval_minutes', 'max_retries')
    def _check_campaign_controls(self):
        for batch in self:
            if batch.batch_size < 1:
                raise UserError(_('Batch Size must be at least 1.'))
            if batch.batch_interval_minutes < 0:
                raise UserError(_('Batch Interval cannot be negative.'))
            if batch.max_retries < 0:
                raise UserError(_('Max Retries cannot be negative.'))


class BirdBulkSendLine(models.Model):
    _name = 'bird.bulk.send.line'
    _description = 'Bird WhatsApp Bulk Send Recipient'
    _order = 'id'

    batch_id = fields.Many2one('bird.bulk.send', required=True, ondelete='cascade', index=True)
    contact_id = fields.Many2one('bird.contact', required=True, ondelete='restrict', index=True)
    phone_number = fields.Char(related='contact_id.whatsapp_number', store=True, readonly=True)
    recipient_count = fields.Integer(string='Recipients', default=1, readonly=True)
    organization_id = fields.Many2one(related='batch_id.organization_id', store=True, readonly=True, index=True)
    channel_id = fields.Many2one(related='batch_id.channel_id', store=True, readonly=True, index=True)
    template_id = fields.Many2one(related='batch_id.template_id', store=True, readonly=True, index=True)
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
    is_read = fields.Boolean(string='Read', default=False, readonly=True, index=True)
    read_at = fields.Datetime(readonly=True)
    failure_code = fields.Char(readonly=True)
    failure_reason = fields.Text(readonly=True)
    auto_retry_allowed = fields.Boolean(default=True, readonly=True)
    message_log_id = fields.Many2one('bird.message.log', readonly=True, ondelete='set null')
    error_message = fields.Text(readonly=True)
