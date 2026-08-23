import base64
import json
import secrets


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
    team_id = fields.Many2one('bird.team', string='Team / Queue', ondelete='set null', index=True)
    assigned_user_id = fields.Many2one(
        'res.users', string='Assigned To', ondelete='set null', index=True, tracking=False,
        domain=[('share', '=', False)],
        help='Internal Odoo user responsible for following up this WhatsApp conversation.',
    )

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
        self._notify_inbox_update('read_changed')
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
    def inbox_get_data(self, filter_name='all', selected_id=False, limit=80, channel_id=False, search_term=False):
        if filter_name == 'closed':
            domain = [('state', '=', 'closed')]
        else:
            domain = [('state', '=', 'open')]
            if filter_name == 'needs_reply':
                domain.append(('needs_reply', '=', True))
            elif filter_name == 'unread':
                domain.append(('unread_count', '>', 0))
            elif filter_name == 'my':
                domain.append(('assigned_user_id', '=', self.env.user.id))
            elif filter_name == 'unassigned':
                domain.append(('assigned_user_id', '=', False))
        if channel_id:
            domain.append(('channel_id', '=', int(channel_id)))
        search_term = (search_term or '').strip()
        if search_term:
            digits = ''.join(ch for ch in search_term if ch.isdigit())
            phone_variants = []
            if digits:
                phone_variants.append(digits)
                stripped = digits.lstrip('0')
                if stripped and stripped not in phone_variants:
                    phone_variants.append(stripped)
                if len(stripped) >= 7:
                    suffix = stripped[-9:]
                    if suffix not in phone_variants:
                        phone_variants.append(suffix)
            # Inbox search is intentionally contact-only: name or phone number.
            # Message body, channel and team are excluded so the search behaves
            # like WhatsApp's conversation/contact search rather than full-text chat search.
            search_parts = [
                ('contact_id.name', 'ilike', search_term),
            ]
            for variant in phone_variants:
                search_parts.append(('contact_id.normalized_number', 'ilike', variant))
            if search_parts:
                domain += ['|'] * (len(search_parts) - 1) + search_parts
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
                'team_id': rec.team_id.id or False, 'team': rec.team_id.name or '',
                'assigned_user_id': rec.assigned_user_id.id or False,
                'assigned_user': rec.assigned_user_id.name or '',
                'tags': [{'id': tag.id, 'name': tag.name, 'color': tag.color} for tag in rec.contact_id.tag_ids],
            })
        selected = False
        # Do not auto-open the first conversation when entering the inbox.
        # A conversation is only considered selected/read after the user clicks it.
        conv = self.browse()
        if selected_id:
            conv = self.sudo().browse(int(selected_id)).exists()
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
                    # Incoming Bird media endpoints are usually protected by AccessKey.
                    # Never expose that credential to the browser; route media through Odoo.
                    'media_url': (f'/bird_connector/conversation_media/{msg.id}' if media_url else ''),
                    'media_mime_type': media_mime,
                    'media_name': media_name,
                    'caption': caption,
                })
            selected = {
                'id': conv.id, 'contact': conv.contact_id.display_name or '',
                'number': conv.contact_id.whatsapp_number or '', 'channel': conv.channel_id.display_name or '',
                'state': conv.state, 'needs_reply': bool(conv.needs_reply), 'messages': messages,
                'team_id': conv.team_id.id or False, 'team': conv.team_id.name or '',
                'assigned_user_id': conv.assigned_user_id.id or False,
                'assigned_user': conv.assigned_user_id.name or '',
                'tags': [{'id': tag.id, 'name': tag.name, 'color': tag.color} for tag in conv.contact_id.tag_ids],
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
        users = self.env['res.users'].sudo().search([('share', '=', False), ('active', '=', True)], order='name, id')
        user_rows = [{'id': user.id, 'name': user.name or user.login or ''} for user in users]
        teams = self.env['bird.team'].sudo().search([('active', '=', True)], order='sequence, name, id')
        team_rows = [{'id': t.id, 'name': t.name, 'member_ids': t.member_ids.ids, 'manager_id': t.manager_id.id or False} for t in teams]
        return {
            'conversations': rows, 'selected': selected, 'channels': channels,
            'users': user_rows, 'teams': team_rows, 'current_user_id': self.env.user.id,
        }

    @api.model
    def inbox_send(self, conversation_id, text, filter_name='all', channel_id=False, search_term=False):
        conv = self.browse(int(conversation_id)).exists()
        if not conv:
            raise UserError(_('Conversation not found.'))
        if conv.state == 'closed':
            raise UserError(_('Reopen this conversation before sending.'))
        conv.reply_message = (text or '').strip()
        conv.action_send_inline()
        return self.inbox_get_data(filter_name or 'all', conv.id, 100, channel_id or False, search_term or False)

    def _public_base_url(self):
        self.ensure_one()
        organization = self.organization_id
        configured = (organization.webhook_base_url or '').strip().rstrip('/') if organization else ''
        system_base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').strip().rstrip('/')
        base_url = configured or system_base
        if not base_url.startswith('https://'):
            raise UserError(_('A public HTTPS Webhook Base URL is required before sending media through Bird.'))
        return base_url

    @api.model
    def inbox_send_media(self, conversation_id, filename, mimetype, data_base64, caption='', filter_name='all', channel_id=False, search_term=False):
        conv = self.browse(int(conversation_id)).exists()
        if not conv:
            raise UserError(_('Conversation not found.'))
        if conv.state == 'closed':
            raise UserError(_('Reopen this conversation before sending.'))

        filename = (filename or 'attachment').strip()[:255]
        mimetype = (mimetype or 'application/octet-stream').strip().lower()
        caption = (caption or '').strip()
        raw_data = (data_base64 or '').strip()
        if not raw_data:
            raise UserError(_('Select a file before sending.'))
        try:
            decoded = base64.b64decode(raw_data, validate=True)
        except Exception:
            raise UserError(_('The selected file could not be decoded.'))
        if not decoded:
            raise UserError(_('The selected file is empty.'))
        max_bytes = 16 * 1024 * 1024
        if len(decoded) > max_bytes:
            raise UserError(_('Attachments sent from the inbox are limited to 16 MB.'))

        message_type = 'image' if mimetype.startswith('image/') else 'file'
        now = fields.Datetime.now()
        token = secrets.token_urlsafe(32)
        msg = self.env['bird.conversation.message'].sudo().create({
            'conversation_id': conv.id,
            'direction': 'outbound',
            'message_type': message_type,
            'body': caption or ('[Image]' if message_type == 'image' else '[Document]'),
            'bird_status': 'sending',
            'message_at': now,
            'media_mime_type': mimetype,
            'media_name': filename,
            'caption': caption or False,
            'media_binary': raw_data,
            'media_token': token,
            'sent_by_user_id': self.env.user.id,
        })
        public_url = f"{conv._public_base_url()}/bird_connector/outbound_media/{msg.id}/{token}"
        msg.sudo().write({'media_url': public_url})

        try:
            if message_type == 'image':
                log = self.env['bird.message.engine'].send_whatsapp_image(
                    conv.channel_id, conv.contact_id.whatsapp_number, public_url, caption=caption or None
                )
            else:
                log = self.env['bird.message.engine'].send_whatsapp_file(
                    conv.channel_id, conv.contact_id.whatsapp_number, public_url,
                    filename=filename, caption=caption or None
                )
        except Exception:
            msg.sudo().write({'bird_status': 'failed'})
            raise

        msg.sudo().write({
            'bird_message_id': log.bird_message_id,
            'bird_status': log.bird_status or log.status,
            'message_at': log.send_date or now,
            'message_log_id': log.id,
        })
        preview = caption or ('[Image]' if message_type == 'image' else f'[Document] {filename}')
        conv.sudo().write({
            'last_message': preview,
            'last_message_at': log.send_date or now,
            'state': 'open',
        })
        conv.contact_id.sudo().write({
            'last_message': preview,
            'last_message_at': log.send_date or now,
            'last_activity_at': log.send_date or now,
        })
        return self.inbox_get_data(filter_name or 'all', conv.id, 100, channel_id or False, search_term or False)

    @api.model
    def inbox_set_team(self, conversation_id, team_id=False):
        conv = self.browse(int(conversation_id)).exists()
        if not conv:
            raise UserError(_('Conversation not found.'))
        team = self.env['bird.team'].sudo().browse(int(team_id)).exists() if team_id else self.env['bird.team']
        vals = {'team_id': team.id if team else False}
        if conv.assigned_user_id and team and conv.assigned_user_id not in team.member_ids and conv.assigned_user_id != team.manager_id:
            vals['assigned_user_id'] = False
        conv.sudo().write(vals)
        conv._notify_inbox_update('team_changed')
        return True

    @api.model
    def inbox_assign(self, conversation_id, user_id=False):
        conv = self.browse(int(conversation_id)).exists()
        if not conv:
            raise UserError(_('Conversation not found.'))
        if user_id:
            user = self.env['res.users'].sudo().browse(int(user_id)).exists()
            if not user or user.share or not user.active:
                raise UserError(_('Select an active internal Odoo user.'))
            if conv.team_id and user not in conv.team_id.member_ids and user != conv.team_id.manager_id:
                raise UserError(_('This user is not a member of the selected Team / Queue.'))
            conv.sudo().write({'assigned_user_id': user.id})
        else:
            conv.sudo().write({'assigned_user_id': False})
        conv._notify_inbox_update('assignment_changed')
        return True

    @api.model
    def inbox_take(self, conversation_id):
        conv = self.browse(int(conversation_id)).exists()
        if not conv:
            raise UserError(_('Conversation not found.'))
        if conv.team_id and self.env.user not in conv.team_id.member_ids and self.env.user != conv.team_id.manager_id:
            raise UserError(_('You are not a member of this Team / Queue.'))
        conv.sudo().write({'assigned_user_id': self.env.user.id})
        conv._notify_inbox_update('conversation_taken')
        return True

    @api.model
    def inbox_set_state(self, conversation_id, state):
        conv = self.browse(int(conversation_id)).exists()
        if not conv:
            return False
        if state == 'closed':
            conv.action_close()
        else:
            conv.action_reopen()
        conv._notify_inbox_update('state_changed')
        return True

    def action_close(self):
        self.write({'state': 'closed'})
        return True

    def action_reopen(self):
        self.write({'state': 'open'})
        return True

    def _notify_inbox_update(self, reason='conversation_changed'):
        """Push a lightweight event so the custom inbox refreshes without a page reload."""
        try:
            self.env['bus.bus']._sendone('bird_status_updates', 'bird_inbox_update', {
                'conversation_ids': self.ids,
                'contact_ids': list(set(self.mapped('contact_id').ids)),
                'reason': reason,
            })
        except Exception:
            # Inbox realtime is best-effort; persisted conversation data must never fail.
            pass
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


    def _apply_auto_routing(self, message_text=''):
        for conv in self:
            # A manual/team assignment wins. Auto-routing only fills an empty queue.
            if conv.team_id:
                continue
            rules = self.env['bird.routing.rule'].sudo().search([('active', '=', True)], order='sequence,id')
            for rule in rules:
                if not rule.matches(conv, message_text=message_text):
                    continue
                vals = {'team_id': rule.team_id.id}
                if rule.assigned_user_id:
                    vals['assigned_user_id'] = rule.assigned_user_id.id
                conv.sudo().write(vals)
                rule.sudo().write({'conversation_count': int(rule.conversation_count or 0) + 1})
                break
        return True

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
        conv._apply_auto_routing(message_text=text or '')
        conv._notify_inbox_update('inbound_message')
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
    media_binary = fields.Binary(string='Outbound Media', attachment=True, readonly=True, copy=False)
    media_token = fields.Char(string='Outbound Media Token', readonly=True, copy=False, index=True)
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
