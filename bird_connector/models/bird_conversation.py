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
    reply_message = fields.Text(string='Reply Message', copy=False)
    needs_reply = fields.Boolean(string='Needs Reply', compute='_compute_needs_reply', store=True, index=True)

    @api.depends('message_ids.direction', 'message_ids.message_at', 'state')
    def _compute_needs_reply(self):
        for rec in self:
            latest = rec.message_ids.sorted(lambda m: (m.message_at or fields.Datetime.from_string('1970-01-01 00:00:00'), m.id), reverse=True)[:1]
            rec.needs_reply = bool(latest and latest.direction == 'inbound' and rec.state == 'open')

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

    def _sync_contact_unread(self):
        for rec in self:
            if not rec.contact_id:
                continue
            total = sum(self.sudo().search([
                ('contact_id', '=', rec.contact_id.id),
                ('state', '=', 'open'),
            ]).mapped('unread_count'))
            rec.contact_id.sudo().write({'unread_count': total})

    def action_mark_read(self):
        for rec in self:
            if rec.unread_count:
                rec.sudo().write({'unread_count': 0})
            rec._sync_contact_unread()
        return True

    def get_formview_action(self, access_uid=None):
        # Opening a conversation is considered reading it. This is also used
        # by Odoo's standard record-to-form navigation in the web client.
        self.ensure_one()
        if self.unread_count:
            self.action_mark_read()
        return super().get_formview_action(access_uid=access_uid)

    def action_send_inline(self):
        self.ensure_one()
        text = (self.reply_message or '').strip()
        if not text:
            raise UserError(_('Type a message before sending.'))
        log = self.env['bird.message.engine'].send_whatsapp_text(
            self.channel_id, self.contact_id.whatsapp_number, text
        )
        now = fields.Datetime.now()
        self.env['bird.conversation.message'].sudo().create({
            'conversation_id': self.id,
            'direction': 'outbound',
            'message_type': 'text',
            'body': text,
            'bird_message_id': log.bird_message_id,
            'bird_status': log.bird_status or log.status,
            'message_at': log.send_date or now,
            'message_log_id': log.id,
            'sent_by_user_id': self.env.user.id,
        })
        self.sudo().write({
            'last_message': text,
            'last_message_at': log.send_date or now,
            'state': 'open',
            'reply_message': False,
        })
        self.contact_id.sudo().write({
            'last_message': text,
            'last_message_at': log.send_date or now,
            'last_activity_at': log.send_date or now,
        })
        return True

    @api.model
    def inbox_get_data(self, filter_name='all', selected_id=False, limit=80, channel_id=False):
        if filter_name == 'closed':
            domain = [('state', '=', 'closed')]
        else:
            domain = [('state', '=', 'open')]
            if filter_name == 'needs_reply':
                domain.append(('needs_reply', '=', True))
            elif filter_name == 'unread':
                domain.append(('unread_count', '>', 0))
        if channel_id:
            domain.append(('channel_id', '=', int(channel_id)))
        conversations = self.sudo().search(domain, order='last_message_at desc, id desc', limit=int(limit or 80))
        if selected_id and int(selected_id) not in conversations.ids:
            extra = self.sudo().browse(int(selected_id)).exists()
            conversations |= extra
        rows = []
        for rec in conversations.sorted(lambda r: (r.last_message_at or fields.Datetime.from_string('1970-01-01 00:00:00'), r.id), reverse=True):
            rows.append({
                'id': rec.id,
                'contact': rec.contact_id.display_name or '',
                'number': rec.contact_id.whatsapp_number or '',
                'channel': rec.channel_id.display_name or '',
                'last_message': rec.last_message or '',
                'last_message_at': fields.Datetime.to_string(rec.last_message_at) if rec.last_message_at else '',
                'unread_count': rec.unread_count or 0,
                'needs_reply': bool(rec.needs_reply),
                'state': rec.state,
            })
        selected = False
        if selected_id:
            conv = self.sudo().browse(int(selected_id)).exists()
        else:
            conv = conversations[:1]
        if conv:
            if conv.unread_count:
                conv.action_mark_read()
            messages = []
            for msg in conv.message_ids.sorted(lambda m: (m.message_at or fields.Datetime.from_string('1970-01-01 00:00:00'), m.id)):
                media_url = msg.media_url or ''
                media_mime = msg.media_mime_type or ''
                media_name = msg.media_name or ''
                caption = msg.caption or ''
                # Backfill display metadata for messages received before v1.9.8
                # without mutating historical rows during a simple inbox read.
                if msg.raw_payload and (not media_url or not caption):
                    try:
                        old_payload = json.loads(msg.raw_payload)
                        _type, _text, old_url, old_mime, old_name, old_caption = self._extract_message_content(old_payload)
                        media_url = media_url or old_url or ''
                        media_mime = media_mime or old_mime or ''
                        media_name = media_name or old_name or ''
                        caption = caption or old_caption or ''
                    except Exception:
                        pass
                messages.append({
                    'id': msg.id, 'direction': msg.direction, 'type': msg.message_type,
                    'body': msg.body or '', 'status': msg.bird_status or '',
                    'message_at': fields.Datetime.to_string(msg.message_at) if msg.message_at else '',
                    'sent_by': msg.sent_by_user_id.name or '',
                    'media_url': media_url,
                    'media_mime_type': media_mime,
                    'media_name': media_name,
                    'caption': caption,
                })
            selected = {
                'id': conv.id, 'contact': conv.contact_id.display_name or '',
                'number': conv.contact_id.whatsapp_number or '', 'channel': conv.channel_id.display_name or '',
                'state': conv.state, 'needs_reply': bool(conv.needs_reply), 'messages': messages,
            }
        channel_domain = [('channel_type', '=', 'whatsapp')]
        channel_records = self.env['bird.channel'].sudo().search(channel_domain, order='name, id')
        channels = []
        for channel in channel_records:
            channels.append({
                'id': channel.id,
                'name': channel.display_name or channel.name or '',
                'workspace': channel.workspace_id.display_name or '',
                'organization': channel.organization_id.display_name or '',
                'state': channel.state or '',
            })
        return {'conversations': rows, 'selected': selected, 'channels': channels}

    @api.model
    def inbox_send(self, conversation_id, text, filter_name='all', channel_id=False):
        conv = self.browse(int(conversation_id)).exists()
        if not conv:
            raise UserError(_('Conversation not found.'))
        if conv.state == 'closed':
            raise UserError(_('Reopen this conversation before sending.'))
        conv.reply_message = (text or '').strip()
        conv.action_send_inline()
        return self.inbox_get_data(filter_name or 'all', conv.id, 100, channel_id or False)

    @api.model
    def inbox_set_state(self, conversation_id, state):
        conv = self.browse(int(conversation_id)).exists()
        if not conv:
            return False
        if state == 'closed':
            conv.action_close()
        else:
            conv.action_reopen()
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
    def _first_media_value(self, value, keys):
        """Best-effort lookup for Bird media metadata across payload versions."""
        if isinstance(value, dict):
            for key in keys:
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            for child in value.values():
                found = self._first_media_value(child, keys)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._first_media_value(child, keys)
                if found:
                    return found
        return False

    @api.model
    def _extract_message_content(self, payload):
        body = payload.get('body') if isinstance(payload, dict) and isinstance(payload.get('body'), dict) else {}
        body_type = str(body.get('type') or 'unknown').lower()
        text = False
        caption = False
        if body_type == 'text' and isinstance(body.get('text'), dict):
            text = body['text'].get('text')
        elif isinstance(body.get('text'), str):
            text = body.get('text')

        # Bird payload shapes have changed over time. Keep the extraction
        # deliberately tolerant so current and older webhook payloads render.
        media_url = self._first_media_value(body, (
            'url', 'mediaUrl', 'media_url', 'downloadUrl', 'download_url',
            'contentUrl', 'content_url', 'sourceUrl', 'source_url',
        ))
        media_mime = self._first_media_value(body, (
            'mimeType', 'mime_type', 'contentType', 'content_type', 'mimetype',
        ))
        media_name = self._first_media_value(body, (
            'filename', 'fileName', 'file_name', 'name', 'title',
        ))
        caption = self._first_media_value(body, ('caption',))

        type_map = {
            'image': 'image', 'video': 'video', 'audio': 'audio', 'voice': 'audio',
            'file': 'file', 'document': 'file', 'text': 'text',
            'interactive': 'interactive', 'template': 'template',
        }
        msg_type = type_map.get(body_type, 'other')
        fallback = {
            'image': '[Image]', 'video': '[Video]', 'audio': '[Audio]',
            'file': '[Document]', 'interactive': '[Interactive]', 'template': '[Template]',
        }.get(msg_type, '[%s]' % body_type.title())
        display_text = text or caption or fallback
        return msg_type, display_text, media_url, media_mime, media_name, caption

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
        msg_type, text, media_url, media_mime, media_name, caption = self._extract_message_content(payload)
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
            'media_url': media_url,
            'media_mime_type': media_mime,
            'media_name': media_name,
            'caption': caption,
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
        ('text', 'Text'), ('template', 'Template'), ('image', 'Image'), ('video', 'Video'),
        ('audio', 'Audio'), ('file', 'File'), ('interactive', 'Interactive'), ('other', 'Other')
    ], default='text', required=True)
    body = fields.Text(string='Message')
    bird_message_id = fields.Char(index=True)
    bird_status = fields.Char(string='Bird Status')
    message_at = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    message_log_id = fields.Many2one('bird.message.log', ondelete='set null', index=True)
    raw_payload = fields.Text(readonly=True)
    media_url = fields.Char(string='Media URL', readonly=True)
    media_mime_type = fields.Char(string='Media MIME Type', readonly=True)
    media_name = fields.Char(string='Media Name', readonly=True)
    caption = fields.Text(string='Caption', readonly=True)
    sent_by_user_id = fields.Many2one('res.users', string='Sent By', readonly=True, ondelete='set null', index=True)


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
            'sent_by_user_id': self.env.user.id,
        })
        conv.sudo().write({'last_message': self.message.strip(), 'last_message_at': log.send_date or now, 'state': 'open'})
        return {'type': 'ir.actions.act_window_close'}
