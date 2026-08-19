import base64
import hashlib
import hmac
import json
import secrets

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BirdWebhookSubscription(models.Model):
    _name = 'bird.webhook.subscription'
    _description = 'Bird Webhook Subscription'
    _order = 'event, channel_id, id'

    organization_id = fields.Many2one('bird.organization', required=True, ondelete='cascade', index=True)
    workspace_id = fields.Many2one('bird.workspace', required=True, ondelete='cascade', index=True)
    channel_id = fields.Many2one('bird.channel', ondelete='cascade', index=True)
    bird_subscription_id = fields.Char(string='Bird Subscription ID', index=True, copy=False)
    service = fields.Char(default='channels', required=True)
    event = fields.Selection([
        ('whatsapp.inbound', 'WhatsApp Inbound'),
        ('whatsapp.outbound', 'WhatsApp Outbound'),
        ('whatsapp.interaction', 'WhatsApp Interaction'),
    ], required=True, index=True)
    webhook_url = fields.Char(string='Webhook URL', required=True)
    signing_key = fields.Char(string='Signing Key', required=True)
    status = fields.Selection([('active', 'Active'), ('inactive', 'Inactive'), ('error', 'Error')], default='active', index=True)
    last_sync_at = fields.Datetime(readonly=True)
    last_event_at = fields.Datetime(readonly=True)
    event_count = fields.Integer(readonly=True)
    last_error = fields.Text(readonly=True)
    raw_response = fields.Text(readonly=True)

    _sql_constraints = [
        ('bird_webhook_unique_event_channel', 'unique(organization_id, channel_id, event)', 'A webhook for this channel and event already exists.'),
    ]

    def action_refresh_from_bird(self):
        for rec in self:
            rec.organization_id.action_sync_webhooks()
        return True

    def action_deactivate_on_bird(self):
        self.ensure_one()
        if not self.bird_subscription_id:
            raise UserError(_('This webhook has no Bird Subscription ID.'))
        result = self.env['bird.api.service'].patch(
            path=f'/workspaces/{self.workspace_id.workspace_id}/webhook-subscriptions/{self.bird_subscription_id}',
            access_key=self.organization_id.access_key,
            payload={'status': 'inactive'},
            timeout=self.organization_id.request_timeout,
        )
        if not result.get('ok'):
            raise UserError(_('Bird webhook update failed (HTTP %s): %s') % (result.get('status_code'), result.get('error')))
        self.write({'status': 'inactive', 'last_sync_at': fields.Datetime.now(), 'raw_response': self.env['bird.api.service'].pretty_json(result.get('data'))})
        return True


class BirdWebhookEvent(models.Model):
    _name = 'bird.webhook.event'
    _description = 'Bird Webhook Event'
    _order = 'received_at desc, id desc'

    organization_id = fields.Many2one('bird.organization', required=True, ondelete='cascade', index=True)
    subscription_id = fields.Many2one('bird.webhook.subscription', ondelete='set null', index=True)
    workspace_external_id = fields.Char(index=True)
    channel_external_id = fields.Char(index=True)
    event = fields.Char(index=True)
    bird_message_id = fields.Char(index=True)
    bird_status = fields.Char(index=True)
    signature_valid = fields.Boolean(default=False, index=True)
    processed = fields.Boolean(default=False, index=True)
    received_at = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    processing_error = fields.Text(readonly=True)
    payload = fields.Text(readonly=True)

    @api.model
    def _deep_find(self, value, keys):
        if isinstance(value, dict):
            for key in keys:
                if value.get(key) not in (None, '', False):
                    return value.get(key)
            for child in value.values():
                found = self._deep_find(child, keys)
                if found not in (None, '', False):
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._deep_find(child, keys)
                if found not in (None, '', False):
                    return found
        return False

    def _process_event(self, data):
        self.ensure_one()
        try:
            event_name = data.get('event') or self.event or ''
            payload = data.get('payload') if isinstance(data.get('payload'), dict) else data
            message_id = self._deep_find(payload, ('messageId', 'message_id', 'id'))
            raw_status = self._deep_find(payload, ('status', 'messageStatus', 'message_status'))
            channel_id = self._deep_find(payload, ('channelId', 'channel_id'))
            if isinstance(raw_status, dict):
                raw_status = raw_status.get('code') or raw_status.get('value') or raw_status.get('status')

            vals = {
                'bird_message_id': str(message_id) if message_id else False,
                'bird_status': str(raw_status) if raw_status else False,
                'channel_external_id': str(channel_id) if channel_id else self.channel_external_id,
            }

            # Phase 1: real-time outbound status application. Inbound content is
            # preserved in bird.webhook.event and becomes Conversations in phase 2.
            if message_id and ('outbound' in event_name or 'interaction' in event_name):
                log = self.env['bird.message.log'].sudo().search([
                    ('organization_id', '=', self.organization_id.id),
                    ('bird_message_id', '=', str(message_id)),
                ], limit=1)
                if log and raw_status:
                    mapped = log._map_status(raw_status)
                    now = fields.Datetime.now()
                    log_vals = {'bird_status': str(raw_status), 'last_status_check_at': now}
                    if mapped:
                        log_vals['status'] = mapped
                        if mapped == 'delivered' and not log.delivered_at:
                            log_vals['delivered_at'] = now
                        elif mapped == 'read' and not log.read_at:
                            log_vals['read_at'] = now
                        elif mapped == 'failed' and not log.failed_at:
                            log_vals['failed_at'] = now
                    log.sudo().write(log_vals)
            vals['processed'] = True
            vals['processing_error'] = False
            self.sudo().write(vals)
        except Exception as exc:
            self.sudo().write({'processed': False, 'processing_error': str(exc)})
        return True
