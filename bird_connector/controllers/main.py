from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class BirdWebhookController(http.Controller):

    @http.route('/webhook/bird/callback', type='json', auth='none', methods=['POST'], csrf=False)
    def bird_webhook_callback(self, **kwargs):
        try:
            raw_data = request.httprequest.get_data(as_text=True)
            payload = json.loads(raw_data) if raw_data else {}
        except Exception:
            payload = kwargs or {}

        _logger.info('Received Bird webhook payload: %s', payload)

        event_type = payload.get('eventType') or payload.get('type') or 'unknown'
        message_data = payload.get('message') or payload.get('data') or payload
        organization_id = payload.get('organizationId') or payload.get('organization_id')

        organization = request.env['bird.organization'].sudo().search([
            ('bird_id', '=', organization_id)
        ], limit=1)

        if not organization:
            _logger.warning('Bird webhook received for unknown organization: %s', organization_id)
            return {'status': 'ignored'}

        if event_type in ['message.created', 'messageStatus.updated', 'message_status.updated']:
            return self._process_message_webhook(organization, payload, message_data, event_type)
        elif event_type in ['conversation.created', 'conversation.updated', 'conversation_status.updated']:
            return self._process_conversation_webhook(organization, payload, event_type)

        return {'status': 'received'}

    def _process_message_webhook(self, organization, payload, message_data, event_type):
        Message = request.env['bird.message'].sudo()
        Conversation = request.env['bird.conversation'].sudo()
        Contact = request.env['bird.contact'].sudo()

        message_id = message_data.get('id') or payload.get('id')
        message_external_id = message_data.get('to') or message_data.get('from')
        status_map = {
            'sent': 'sent',
            'delivered': 'delivered',
            'read': 'read',
            'failed': 'failed',
            'delivery_failed': 'failed',
        }
        raw_status = message_data.get('status') or message_data.get('statusType') or 'pending'
        mapped_status = status_map.get(raw_status.lower() if isinstance(raw_status, str) else raw_status, 'pending')

        message_vals = {
            'organization_id': organization.id,
            'message_id': message_id,
            'status': mapped_status,
            'payload': json.dumps(payload, ensure_ascii=False),
            'body': message_data.get('body') or message_data.get('content', {}).get('text') or '',
            'media_url': message_data.get('media', {}).get('url') if isinstance(message_data.get('media'), dict) else message_data.get('mediaUrl'),
        }

        channel_id_val = message_data.get('channelId') or message_data.get('channel_id')
        if channel_id_val:
            channel = request.env['bird.channel'].sudo().search([
                ('channel_id', '=', channel_id_val),
            ], limit=1)
            if channel:
                message_vals['channel_id'] = channel.id

        conversation_id_val = message_data.get('conversationId') or message_data.get('conversation_id') or message_data.get('conversation', {}).get('id')
        if conversation_id_val:
            conversation = Conversation.search([
                ('conversation_id', '=', conversation_id_val),
            ], limit=1)
            if conversation:
                message_vals['conversation_id'] = conversation.id
            else:
                new_conv = self._ensure_conversation(organization, message_data)
                if new_conv:
                    message_vals['conversation_id'] = new_conv.id

        contact_id_val = message_data.get('contactId') or message_data.get('contact_id') or message_data.get('from') if isinstance(message_data.get('from'), str) and not message_data.get('to') else message_data.get('to')
        if contact_id_val:
            contact = Contact.search([
                ('contact_id', '=', contact_id_val),
            ], limit=1)
            if contact:
                message_vals['contact_id'] = contact.id

        direction = message_data.get('direction') or 'outbound'
        message_vals['direction'] = direction if direction in ['inbound', 'outbound'] else 'outbound'

        if mapped_status == 'failed':
            message_vals['error_message'] = message_data.get('error', {}).get('description', '') if isinstance(message_data.get('error'), dict) else str(message_data.get('error', ''))

        ts = message_data.get('sentAt') or message_data.get('createdAt')
        if ts:
            from datetime import datetime
            try:
                message_vals['sent_at'] = datetime.fromtimestamp(int(ts) / 1000 if int(ts) > 1e12 else int(ts))
            except Exception:
                pass

        existing = Message.search([('message_id', '=', message_id)], limit=1)
        if existing:
            existing.write(message_vals)
        else:
            Message.create(message_vals)

        self._update_conversation_timestamp(organization, message_data)
        return {'status': 'processed'}

    def _process_conversation_webhook(self, organization, payload, event_type):
        Conversation = request.env['bird.conversation'].sudo()
        conv_data = payload.get('conversation') or payload.get('data') or payload
        conv_id = conv_data.get('id') or payload.get('id')

        vals = {
            'organization_id': organization.id,
            'conversation_id': conv_id,
            'contact_name': conv_data.get('contact', {}).get('displayName') if isinstance(conv_data.get('contact'), dict) else conv_data.get('contactDisplayName'),
            'contact_phone': conv_data.get('contact', {}).get('phoneNumber') if isinstance(conv_data.get('contact'), dict) else conv_data.get('contactPhoneNumber'),
            'status': conv_data.get('status', 'active'),
        }

        channel_id_val = conv_data.get('channelId') or payload.get('channelId')
        if channel_id_val:
            channel = request.env['bird.channel'].sudo().search([('channel_id', '=', channel_id_val)], limit=1)
            if channel:
                vals['channel_id'] = channel.id

        workspace_id_val = conv_data.get('workspaceId') or payload.get('workspaceId')
        if workspace_id_val:
            workspace = request.env['bird.workspace'].sudo().search([('workspace_id', '=', workspace_id_val)], limit=1)
            if workspace:
                vals['workspace_id'] = workspace.id

        existing = Conversation.search([('conversation_id', '=', conv_id)], limit=1)
        if existing:
            existing.write(vals)
        else:
            Conversation.create(vals)
        return {'status': 'processed'}

    def _ensure_conversation(self, organization, message_data):
        Conversation = request.env['bird.conversation'].sudo()
        conv_id = message_data.get('conversationId') or message_data.get('conversation_id') or message_data.get('conversation', {}).get('id')
        if not conv_id:
            return None
        return Conversation.search([('conversation_id', '=', conv_id)], limit=1) or None

    def _update_conversation_timestamp(self, organization, message_data):
        Conversation = request.env['bird.conversation'].sudo()
        conv_id = message_data.get('conversationId') or message_data.get('conversation_id') or message_data.get('conversation', {}).get('id')
        if not conv_id:
            return
        conversation = Conversation.search([('conversation_id', '=', conv_id)], limit=1)
        if not conversation:
            conv_vals = {
                'organization_id': organization.id,
                'conversation_id': conv_id,
                'last_message_at': fields.Datetime.now(),
            }
            channel_id_val = message_data.get('channelId')
            if channel_id_val:
                channel = self.env['bird.channel'].sudo().search([('channel_id', '=', channel_id_val)], limit=1)
                if channel:
                    conv_vals['channel_id'] = channel.id
            conversation = Conversation.create(conv_vals)
        conversation.write({'last_message_at': fields.Datetime.now()})
