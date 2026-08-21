import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BirdContactTag(models.Model):
    _name = 'bird.contact.tag'
    _description = 'Bird Contact Tag'
    _order = 'name, id'

    name = fields.Char(required=True, index=True, translate=False)
    color = fields.Integer(string='Color')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('bird_contact_tag_name_unique', 'unique(name)', 'A Bird contact tag with this name already exists.'),
    ]


class BirdContact(models.Model):
    _name = 'bird.contact'
    _description = 'Bird Contact'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'last_activity_at desc, name, id'
    _rec_name = 'display_name'

    name = fields.Char(string='Contact Name', tracking=True, index=True)
    display_name = fields.Char(compute='_compute_display_name', store=True, index=True)
    whatsapp_number = fields.Char(string='WhatsApp Number', required=True, tracking=True, index=True)
    normalized_number = fields.Char(string='Normalized Number', required=True, index=True, copy=False)
    tag_ids = fields.Many2many(
        'bird.contact.tag',
        'bird_contact_tag_rel',
        'contact_id',
        'tag_id',
        string='Tags',
        tracking=True,
    )

    organization_id = fields.Many2one(
        'bird.organization',
        string='Organization',
        required=True,
        ondelete='cascade',
        index=True,
    )
    workspace_id = fields.Many2one(
        'bird.workspace',
        string='Workspace',
        required=True,
        ondelete='cascade',
        index=True,
    )
    channel_id = fields.Many2one(
        'bird.channel',
        string='Last Channel',
        ondelete='set null',
        index=True,
    )
    bird_contact_id = fields.Char(string='Bird Contact ID', index=True, copy=False)

    linked_partner_id = fields.Many2one(
        'res.partner',
        string='Linked Odoo Contact',
        ondelete='set null',
        index=True,
        help='Optional link to an official Odoo contact. Bird contacts remain separate unless you link them manually.',
    )

    last_message = fields.Text(string='Last Message', readonly=True)
    last_message_at = fields.Datetime(string='Last Message At', readonly=True, index=True)
    last_activity_at = fields.Datetime(string='Last Activity', readonly=True, index=True)
    unread_count = fields.Integer(string='Unread', default=0, readonly=True)
    conversation_ids = fields.One2many('bird.conversation', 'contact_id', string='Conversations')
    conversation_count = fields.Integer(compute='_compute_conversation_count')
    state = fields.Selection(
        [('active', 'Active'), ('archived', 'Archived')],
        default='active',
        required=True,
        tracking=True,
        index=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            'bird_contact_workspace_number_unique',
            'unique(workspace_id, normalized_number)',
            'This WhatsApp number already exists as a Bird contact in this workspace.',
        ),
    ]

    @staticmethod
    def _normalize_phone(value):
        """Return a stable E.164-like key without changing the visible number."""
        value = str(value or '').strip()
        if not value:
            return ''
        # Bird normally supplies +E.164 values. Keeping only digits avoids
        # duplicates caused by spaces, dashes or brackets while preserving the
        # original value in whatsapp_number for display.
        return re.sub(r'\D+', '', value)

    @api.depends('name', 'whatsapp_number')
    def _compute_display_name(self):
        for rec in self:
            if rec.name and rec.whatsapp_number:
                rec.display_name = '%s (%s)' % (rec.name, rec.whatsapp_number)
            else:
                rec.display_name = rec.name or rec.whatsapp_number or _('Bird Contact')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            number = vals.get('whatsapp_number')
            vals['normalized_number'] = self._normalize_phone(number)
            if not vals['normalized_number']:
                raise ValidationError(_('WhatsApp Number is required.'))
            workspace = self.env['bird.workspace'].browse(vals.get('workspace_id'))
            if workspace.exists() and not vals.get('organization_id'):
                vals['organization_id'] = workspace.organization_id.id
        return super().create(vals_list)

    def write(self, vals):
        if 'whatsapp_number' in vals:
            vals['normalized_number'] = self._normalize_phone(vals.get('whatsapp_number'))
            if not vals['normalized_number']:
                raise ValidationError(_('WhatsApp Number is required.'))
        return super().write(vals)

    def _compute_conversation_count(self):
        for rec in self:
            rec.conversation_count = len(rec.conversation_ids)

    def action_open_conversations(self):
        self.ensure_one()
        action = self.env.ref('bird_connector.action_bird_conversation').read()[0]
        action['domain'] = [('contact_id', '=', self.id)]
        action['context'] = {'default_contact_id': self.id, 'default_workspace_id': self.workspace_id.id, 'default_channel_id': self.channel_id.id}
        return action

    def action_mark_read(self):
        self.write({'unread_count': 0})
        return True

    def action_archive_contact(self):
        self.write({'state': 'archived', 'active': False})
        return True

    def action_restore_contact(self):
        self.with_context(active_test=False).write({'state': 'active', 'active': True})
        return True


    def action_open_bulk_send_message(self):
        contacts = self.exists()
        if not contacts:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send WhatsApp Message'),
            'res_model': 'bird.send.message.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'bird.contact',
                'active_ids': contacts.ids,
                'default_contact_ids': [(6, 0, contacts.ids)],
                'bird_bulk_mode': True,
            },
        }

    @api.model
    def _upsert_from_inbound(self, organization, subscription, payload, event_time=None):
        """Create or update the Bird-only contact represented by an inbound event.

        This deliberately does *not* create ``res.partner`` records. It keeps
        WhatsApp/Bird identities isolated from Odoo's accounting/business
        contacts unless a user explicitly links one later.
        """
        if not isinstance(payload, dict):
            return self.browse()

        sender = payload.get('sender') if isinstance(payload.get('sender'), dict) else {}
        contact_data = sender.get('contact') if isinstance(sender.get('contact'), dict) else {}
        number = (
            contact_data.get('identifierValue')
            or contact_data.get('identifier')
            or sender.get('identifierValue')
            or sender.get('phoneNumber')
            or sender.get('phone')
        )
        normalized = self._normalize_phone(number)
        if not normalized:
            return self.browse()

        workspace = subscription.workspace_id if subscription else self.env['bird.workspace'].search([
            ('organization_id', '=', organization.id),
            ('workspace_id', '=', organization.workspace_id),
        ], limit=1)
        if not workspace:
            return self.browse()

        channel = subscription.channel_id if subscription else self.env['bird.channel'].search([
            ('workspace_id', '=', workspace.id),
            ('channel_id', '=', str(payload.get('channelId') or '')),
        ], limit=1)

        annotations = contact_data.get('annotations') if isinstance(contact_data.get('annotations'), dict) else {}
        sender_annotations = sender.get('annotations') if isinstance(sender.get('annotations'), dict) else {}
        contact_name = annotations.get('name') or sender_annotations.get('name') or contact_data.get('name') or sender.get('name')
        bird_contact_id = contact_data.get('id') or sender.get('contactId')

        body = payload.get('body') if isinstance(payload.get('body'), dict) else {}
        body_type = body.get('type')
        message_text = False
        if body_type == 'text' and isinstance(body.get('text'), dict):
            message_text = body['text'].get('text')
        elif isinstance(body.get('text'), str):
            message_text = body.get('text')
        if not message_text:
            # Useful compact fallback for media until Conversations adds richer
            # message rendering in the next phase.
            message_text = ('[%s]' % body_type.title()) if body_type else False

        contact = self.with_context(active_test=False).search([
            ('workspace_id', '=', workspace.id),
            ('normalized_number', '=', normalized),
        ], limit=1)

        now = event_time or fields.Datetime.now()
        vals = {
            'organization_id': organization.id,
            'workspace_id': workspace.id,
            'channel_id': channel.id if channel else False,
            'whatsapp_number': str(number),
            'normalized_number': normalized,
            'last_message_at': now,
            'last_activity_at': now,
            'active': True,
            'state': 'active',
        }
        if contact_name:
            vals['name'] = str(contact_name)
        if bird_contact_id:
            vals['bird_contact_id'] = str(bird_contact_id)
        if message_text:
            vals['last_message'] = str(message_text)

        if contact:
            vals['unread_count'] = int(contact.unread_count or 0) + 1
            contact.sudo().write(vals)
        else:
            vals['unread_count'] = 1
            contact = self.sudo().create(vals)
        return contact
