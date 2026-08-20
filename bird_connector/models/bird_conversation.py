import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BirdConversation(models.Model):
    _name = 'bird.conversation'
    _description = 'Bird Conversation'
    _order = 'last_message_at desc, id desc'
    _rec_name = 'contact_id'

    contact_id = fields.Many2one('bird.contact', required=True, ondelete='cascade', index=True)
    organization_id = fields.Many2one('bird.organization', related='contact_id.organization_id', store=True, index=True)
    workspace_id = fields.Many2one('bird.workspace', required=True, ondelete='cascade', index=True)
    channel_id = fields.Many2one('bird.channel', required=True, ondelete='cascade', index=True)
    message_ids = fields.One2many('bird.conversation.message', 'conversation_id', string='Messages')
    message_count = fields.Integer(compute='_compute_counts')
    unread_count = fields.Integer(default=0, readonly=True, index=True)
    last_message = fields.Text(readonly=True)
    last_message_at = fields.Datetime(readonly=True, index=True)
    state = fields.Selection([('open', 'Open'), ('closed', 'Closed')], default='open', required=True, index=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('bird_conversation_contact_channel_unique', 'unique(contact_id, channel_id)',
         'A conversation already exists for this Bird contact and channel.'),
    ]

    @api.depends('message_ids')
    def _compute_counts(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)

    def action_reply(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Reply'),
            'res_model': 'bird.conversation.reply.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_conversation_id': self.id},
        }

    def action_mark_read(self):
        for rec in self:
            rec.write({'unread_count': 0})
            rec.contact_id.sudo().write({'unread_count': 0})
        return True

    def action_close(self):
        self.write({'state': 'closed'})
        return True

    def action_reopen(self):
        self.write({'state': 'open'})
        return True

    @api.model
    def _get_or_create(self, contact, channel):
        if not contact or not channel:
            return self.browse()
        conv = self.sudo().search([
            ('contact_id', '=', contact.id),
            ('channel_id', '=', channel.id),
        ], limit=1)
        if not conv:
            conv = self.sudo().create({
                'contact_id': contact.id,
                'workspace_id': contact.workspace_id.id,
                'channel_id': channel.id,
            })
        return conv

    @api.model
    def _extract_message_text(self, payload):
        body = payload.get('body') if isinstance(payload, dict) and isinstance(payload.get('body'), dict) else {}
        body_type = body.get('type') or 'unknown'
        text = False
        if body_type == 'text' and isinstance(body.get('text'), dict):
            text = body['text'].get('text')
        elif isinstance(body.get('text'), str):
            text = body.get('text')
        return body_type, text or ('[%s]' % str(body_type).title())

    @api.model
    def _record_inbound(self, contact, channel, payload, message_id=False, event_time=None, status=False):
        conv = self._get_or_create(contact, channel)
        if not conv:
            return self.env['bird.conversation.message']
        if message_id:
            existing = self.env['bird.conversation.message'].sudo().search([
                ('bird_message_id', '=', str(message_id)),
                ('direction', '=', 'inbound'),
            ], limit=1)
            if existing:
                return existing
        msg_type, text = self._extract_message_text(payload)
        when = event_time or fields.Datetime.now()
        msg = self.env['bird.conversation.message'].sudo().create({
            'conversation_id': conv.id,
            'direction': 'inbound',
            'message_type': msg_type if msg_type in dict(self.env['bird.conversation.message']._fields['message_type'].selection) else 'other',
            'body': text,
            'bird_message_id': str(message_id) if message_id else False,
            'bird_status': str(status) if status else False,
            'message_at': when,
            'raw_payload': json.dumps(payload, ensure_ascii=False, indent=2),
        })
        conv.sudo().write({
            'last_message': text,
            'last_message_at': when,
            'unread_count': int(conv.unread_count or 0) + 1,
            'state': 'open',
        })
        return msg


class BirdConversationMessage(models.Model):
    _name = 'bird.conversation.message'
    _description = 'Bird Conversation Message'
    _order = 'message_at asc, id asc'

    conversation_id = fields.Many2one('bird.conversation', required=True, ondelete='cascade', index=True)
    contact_id = fields.Many2one('bird.contact', related='conversation_id.contact_id', store=True, index=True)
    channel_id = fields.Many2one('bird.channel', related='conversation_id.channel_id', store=True, index=True)
    direction = fields.Selection([('inbound', 'Incoming'), ('outbound', 'Outgoing')], required=True, index=True)
    message_type = fields.Selection([
        ('text', 'Text'), ('template', 'Template'), ('image', 'Image'), ('file', 'File'),
        ('interactive', 'Interactive'), ('other', 'Other')
    ], default='text', required=True)
    body = fields.Text(string='Message')
    bird_message_id = fields.Char(index=True)
    bird_status = fields.Char(string='Bird Status')
    message_at = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    message_log_id = fields.Many2one('bird.message.log', ondelete='set null', index=True)
    raw_payload = fields.Text(readonly=True)


class BirdConversationReplyWizard(models.TransientModel):
    _name = 'bird.conversation.reply.wizard'
    _description = 'Reply to Bird Conversation'

    conversation_id = fields.Many2one('bird.conversation', required=True, readonly=True)
    contact_id = fields.Many2one(related='conversation_id.contact_id', readonly=True)
    channel_id = fields.Many2one(related='conversation_id.channel_id', readonly=True)
    message = fields.Text(required=True)

    def action_send(self):
        self.ensure_one()
        if not self.message or not self.message.strip():
            raise UserError(_('Message text is required.'))
        conv = self.conversation_id
        log = self.env['bird.message.engine'].send_whatsapp_text(
            conv.channel_id, conv.contact_id.whatsapp_number, self.message.strip()
        )
        now = fields.Datetime.now()
        self.env['bird.conversation.message'].sudo().create({
            'conversation_id': conv.id,
            'direction': 'outbound',
            'message_type': 'text',
            'body': self.message.strip(),
            'bird_message_id': log.bird_message_id,
            'bird_status': log.bird_status or log.status,
            'message_at': log.send_date or now,
            'message_log_id': log.id,
        })
        conv.sudo().write({'last_message': self.message.strip(), 'last_message_at': log.send_date or now, 'state': 'open'})
        return {'type': 'ir.actions.act_window_close'}
