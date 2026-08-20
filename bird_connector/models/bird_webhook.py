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
    signing_key = fields.Char(
        string='Signing Key',
        help='Only stored for webhook subscriptions managed by this Odoo connector. Bird does not expose signing keys when listing existing subscriptions.',
    )
    managed_by_connector = fields.Boolean(
        string='Managed by Odoo',
        default=False,
        readonly=True,
        index=True,
        help='Enabled when the subscription URL belongs to this Bird Connector organization.',
    )
    ownership = fields.Selection(
        [('odoo', 'Odoo Connector'), ('external', 'External / Existing')],
        string='Ownership',
        compute='_compute_ownership',
        store=True,
        index=True,
    )
    status = fields.Selection([('active', 'Active'), ('inactive', 'Inactive'), ('error', 'Error')], default='active', index=True)
    last_sync_at = fields.Datetime(readonly=True)
    last_event_at = fields.Datetime(readonly=True)
    event_count = fields.Integer(readonly=True)
    last_error = fields.Text(readonly=True)
    raw_response = fields.Text(readonly=True)

    _sql_constraints = [
        ('bird_webhook_unique_remote_id', 'unique(organization_id, bird_subscription_id)', 'This Bird webhook subscription is already synchronized.'),
    ]

    @api.depends('managed_by_connector')
    def _compute_ownership(self):
        for rec in self:
            rec.ownership = 'odoo' if rec.managed_by_connector else 'external'

    def init(self):
        # V1.9.0 incorrectly assumed one subscription per event/channel.
        # Bird allows several subscriptions for the same event/channel when they
        # point to different URLs. Remove the legacy constraint during upgrade.
        self.env.cr.execute(
            'ALTER TABLE bird_webhook_subscription '
            'DROP CONSTRAINT IF EXISTS bird_webhook_unique_event_channel'
        )

    def action_refresh_from_bird(self):
        self.ensure_one()
        self.organization_id.action_sync_webhooks()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_deactivate_on_bird(self):
        self.ensure_one()
        if not self.managed_by_connector:
            raise UserError(_('Only webhook subscriptions managed by this Odoo connector can be deactivated from Odoo.'))
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

            # Keep Bird messaging identities separate from res.partner. Each
            # inbound WhatsApp event creates/updates a Bird Contact and increments
            # its unread counter. Conversations will build on this contact model.
            if 'inbound' in event_name:
                # Bird can retry a webhook. Do not count the same inbound message
                # as unread twice when an identical message ID was already
                # processed successfully.
                duplicate = False
                if message_id:
                    duplicate = bool(self.sudo().search_count([
                        ('id', '!=', self.id),
                        ('organization_id', '=', self.organization_id.id),
                        ('event', '=', event_name),
                        ('bird_message_id', '=', str(message_id)),
                        ('processed', '=', True),
                    ]))
                if not duplicate:
                    subscription = self.subscription_id
                    contact = self.env['bird.contact'].sudo()._upsert_from_inbound(
                        self.organization_id,
                        subscription,
                        payload,
                        event_time=self.received_at or fields.Datetime.now(),
                    )
                    channel = subscription.channel_id if subscription else False
                    if contact and channel:
                        self.env['bird.conversation'].sudo()._record_inbound(
                            contact, channel, payload, message_id=message_id,
                            event_time=self.received_at or fields.Datetime.now(), status=raw_status,
                        )

            # Real-time outbound status application.
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
                    conv_msg = self.env['bird.conversation.message'].sudo().search([
                        ('bird_message_id', '=', str(message_id)), ('direction', '=', 'outbound')
                    ], limit=1)
                    if conv_msg:
                        conv_msg.sudo().write({'bird_status': str(raw_status)})
            vals['processed'] = True
            vals['processing_error'] = False
            self.sudo().write(vals)
        except Exception as exc:
            self.sudo().write({'processed': False, 'processing_error': str(exc)})
        return True
