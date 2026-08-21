import re
from urllib.parse import quote

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
        default=lambda self: self.env['bird.organization'].search([('state','=','active')], limit=1),
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
    bird_contact_id = fields.Char(string='Bird Contact ID', index=True, copy=False, tracking=True)
    bird_sync_status = fields.Selection(
        [('not_synced', 'Not Synced'), ('synced', 'Synced'), ('error', 'Sync Error')],
        string='Bird Sync Status',
        default='not_synced',
        readonly=True,
        copy=False,
        tracking=True,
    )
    bird_synced_at = fields.Datetime(string='Bird Synced At', readonly=True, copy=False)
    bird_sync_error = fields.Text(string='Bird Sync Error', readonly=True, copy=False)

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
        """Return the canonical digits-only lookup key.

        This method intentionally remains country-agnostic because it is also
        used for matching numbers already returned by Bird in +E.164 format.
        Country-aware formatting is handled by :meth:`_format_phone_e164`.
        """
        value = str(value or '').strip()
        if not value:
            return ''
        return re.sub(r'\D+', '', value)

    @api.model
    def _default_phone_country(self, organization=None):
        """Resolve the country used for local-number normalization."""
        organization = organization or self.env['bird.organization'].browse()
        if organization and organization.default_country_id:
            return organization.default_country_id
        active_org = self.env['bird.organization'].search([('state', '=', 'active')], limit=1)
        if active_org and active_org.default_country_id:
            return active_org.default_country_id
        return self.env.ref('base.sa', raise_if_not_found=False)

    @api.model
    def _format_phone_e164(self, value, organization=None):
        """Normalize a WhatsApp number to a displayable E.164-style value.

        Supported examples when the organization country is Saudi Arabia:
        ``0501234567``, ``501234567``, ``966501234567``,
        ``00966501234567`` and ``+966501234567`` all become
        ``+966501234567``.

        Bird-provided international numbers are preserved as international
        values and are never re-prefixed with the default country code.
        """
        raw = str(value or '').strip()
        if not raw:
            return ''

        compact = re.sub(r'[\s\-().]', '', raw)
        if compact.startswith('00'):
            compact = '+' + compact[2:]

        digits = re.sub(r'\D+', '', compact)
        if not digits:
            return ''

        # Explicit + numbers are already international.
        if compact.startswith('+'):
            return '+' + digits

        country = self._default_phone_country(organization=organization)
        phone_code = str(getattr(country, 'phone_code', '') or '').strip()
        phone_code = re.sub(r'\D+', '', phone_code)

        # If no default country can be resolved, keep a deterministic +digits
        # representation rather than guessing a country code.
        if not phone_code:
            return '+' + digits

        # Number already entered with the selected country code but without +.
        if digits.startswith(phone_code):
            return '+' + digits

        # Remove the national trunk prefix (normally 0) before adding the
        # country dialing code. Multiple leading zeroes are tolerated.
        national = digits.lstrip('0') if digits.startswith('0') else digits
        if not national:
            return ''
        return '+' + phone_code + national

    @api.onchange('whatsapp_number', 'organization_id')
    def _onchange_whatsapp_number_normalize(self):
        for rec in self:
            raw_digits = self._normalize_phone(rec.whatsapp_number)
            # Avoid rewriting the field while the user is still typing a very
            # short/incomplete value. Final normalization is always enforced
            # again in create()/write().
            if len(raw_digits) >= 7:
                formatted = self._format_phone_e164(rec.whatsapp_number, organization=rec.organization_id)
                if formatted:
                    rec.whatsapp_number = formatted

    @api.depends('name', 'whatsapp_number')
    def _compute_display_name(self):
        for rec in self:
            if rec.name and rec.whatsapp_number:
                rec.display_name = '%s (%s)' % (rec.name, rec.whatsapp_number)
            else:
                rec.display_name = rec.name or rec.whatsapp_number or _('Bird Contact')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        organization = self.env['bird.organization'].browse(vals.get('organization_id')).exists()
        if not organization:
            organization = self.env['bird.organization'].search([('state', '=', 'active')], limit=1)
            if organization and 'organization_id' in fields_list:
                vals['organization_id'] = organization.id
        if organization and not vals.get('workspace_id') and 'workspace_id' in fields_list:
            workspace = self.env['bird.workspace'].search([('organization_id', '=', organization.id)], limit=1)
            if workspace:
                vals['workspace_id'] = workspace.id
        return vals

    @api.onchange('organization_id')
    def _onchange_organization_id(self):
        if self.organization_id and (not self.workspace_id or self.workspace_id.organization_id != self.organization_id):
            self.workspace_id = self.env['bird.workspace'].search([('organization_id', '=', self.organization_id.id)], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            number = vals.get('whatsapp_number')
            workspace = self.env['bird.workspace'].browse(vals.get('workspace_id')).exists()
            organization = self.env['bird.organization'].browse(vals.get('organization_id')).exists()
            if workspace and not organization:
                organization = workspace.organization_id
                vals['organization_id'] = organization.id
            if organization and not workspace:
                workspace = self.env['bird.workspace'].search([('organization_id', '=', organization.id)], limit=1)
                if workspace:
                    vals['workspace_id'] = workspace.id
            if not organization:
                organization = self.env['bird.organization'].search([('state', '=', 'active')], limit=1)
                if organization:
                    vals['organization_id'] = organization.id
            if not workspace and organization:
                workspace = self.env['bird.workspace'].search([('organization_id', '=', organization.id)], limit=1)
                if workspace:
                    vals['workspace_id'] = workspace.id
            if not vals.get('organization_id') or not vals.get('workspace_id'):
                raise ValidationError(_('Configure at least one active Bird Organization and Workspace before creating Bird contacts manually.'))

            organization = self.env['bird.organization'].browse(vals.get('organization_id')).exists()
            formatted = self._format_phone_e164(number, organization=organization)
            normalized = self._normalize_phone(formatted)
            if not normalized:
                raise ValidationError(_('WhatsApp Number is required.'))
            vals['whatsapp_number'] = formatted
            vals['normalized_number'] = normalized
        records = super().create(vals_list)
        # Contacts created manually in Odoo should immediately gain the same
        # canonical identity used by Bird.  Do not make contact creation fail
        # merely because Bird is temporarily unavailable; the user can retry
        # from the form with the Sync Bird Contact button.
        for rec in records:
            if not rec.bird_contact_id and not self.env.context.get('skip_bird_contact_sync'):
                rec._sync_bird_contact_identity(raise_on_error=False)
        return records

    def write(self, vals):
        if 'whatsapp_number' in vals:
            # A multi-record write may contain contacts from different Bird
            # organizations/countries. Normalize per record in that case.
            if len(self) > 1:
                result = True
                for rec in self:
                    rec_vals = dict(vals)
                    formatted = rec._format_phone_e164(
                        rec_vals.get('whatsapp_number'),
                        organization=rec.organization_id,
                    )
                    normalized = rec._normalize_phone(formatted)
                    if not normalized:
                        raise ValidationError(_('WhatsApp Number is required.'))
                    rec_vals['whatsapp_number'] = formatted
                    rec_vals['normalized_number'] = normalized
                    result = super(BirdContact, rec).write(rec_vals) and result
                return result

            organization = self.organization_id
            if vals.get('organization_id'):
                organization = self.env['bird.organization'].browse(vals['organization_id']).exists()
            formatted = self._format_phone_e164(vals.get('whatsapp_number'), organization=organization)
            vals['normalized_number'] = self._normalize_phone(formatted)
            vals['whatsapp_number'] = formatted
            if not vals['normalized_number']:
                raise ValidationError(_('WhatsApp Number is required.'))
        return super().write(vals)

    def _extract_bird_contact_from_search(self, data):
        """Return the first Bird contact object from a Contacts search response."""
        if not isinstance(data, dict):
            return {}
        for key in ('results', 'contacts', 'items', 'data'):
            value = data.get(key)
            if isinstance(value, list) and value:
                return value[0] if isinstance(value[0], dict) else {}
            if isinstance(value, dict) and value.get('id'):
                return value
        if data.get('id'):
            return data
        return {}

    def _sync_bird_contact_identity(self, raise_on_error=False):
        """Resolve or create this contact in Bird and persist its real Bird ID.

        V1.9.22 deliberately uses Bird's documented Contacts search + create
        flow rather than relying only on PATCH-by-identifier.  This is more
        transparent for manually-created Odoo contacts:

        1. search Bird by the canonical ``phonenumber`` identifier;
        2. reuse the existing Bird contact when found;
        3. otherwise create a new Bird contact with that identifier;
        4. handle a create race/duplicate by searching once more.

        The phone value is always E.164 (for example ``+966501234567``).
        """
        api_service = self.env['bird.api.service']
        for rec in self:
            def fail(message):
                rec.with_context(skip_bird_contact_sync=True).sudo().write({
                    'bird_sync_status': 'error',
                    'bird_sync_error': message,
                })
                if raise_on_error:
                    raise ValidationError(_('Bird Contact synchronization failed: %s') % message)

            if not rec.workspace_id or not rec.organization_id:
                fail(_('Organization and Workspace are required before syncing the Bird contact.'))
                continue
            workspace_uid = rec.workspace_id.workspace_id
            if not workspace_uid:
                fail(_('Bird Workspace ID is missing on the selected workspace.'))
                continue
            access_key = rec.organization_id.access_key
            if not access_key:
                fail(_('Bird API Access Key is missing on the selected organization.'))
                continue

            phone = rec._format_phone_e164(rec.whatsapp_number, organization=rec.organization_id)
            if not phone:
                fail(_('A valid WhatsApp number is required before syncing the Bird contact.'))
                continue

            timeout = rec.organization_id.request_timeout
            search_path = f'/workspaces/{workspace_uid}/contacts/search'
            search_payload = {
                'identifier': {
                    'key': 'phonenumber',
                    'value': phone,
                }
            }

            # Bird documents this as POST. Some older examples show GET with a
            # JSON body, so keep a compatibility fallback for older tenants.
            search_result = api_service.post(
                path=search_path,
                access_key=access_key,
                payload=search_payload,
                timeout=timeout,
            )
            if not search_result.get('ok') and search_result.get('status_code') in (404, 405):
                search_result = api_service.request(
                    'GET',
                    search_path,
                    access_key,
                    payload=search_payload,
                    timeout=timeout,
                )

            bird_contact = rec._extract_bird_contact_from_search(search_result.get('data') or {})
            bird_id = bird_contact.get('id') if bird_contact else False

            if not bird_id:
                create_path = f'/workspaces/{workspace_uid}/contacts'
                create_payload = {
                    'displayName': rec.name or phone,
                    'identifiers': [
                        {
                            'key': 'phonenumber',
                            'value': phone,
                        }
                    ],
                }
                create_result = api_service.post(
                    path=create_path,
                    access_key=access_key,
                    payload=create_payload,
                    timeout=timeout,
                )
                create_data = create_result.get('data') or {}
                if isinstance(create_data, dict):
                    bird_id = create_data.get('id')

                # A 409 can happen when another Bird process created the same
                # identifier between our search and create. Resolve it again.
                if not bird_id and create_result.get('status_code') == 409:
                    retry_search = api_service.post(
                        path=search_path,
                        access_key=access_key,
                        payload=search_payload,
                        timeout=timeout,
                    )
                    bird_contact = rec._extract_bird_contact_from_search(retry_search.get('data') or {})
                    bird_id = bird_contact.get('id') if bird_contact else False

                if not bird_id:
                    # Prefer the create error when creation was attempted; it
                    # is normally more actionable than an empty search result.
                    message = create_result.get('error') or search_result.get('error') or _('Bird did not return a Contact ID.')
                    status_code = create_result.get('status_code') or search_result.get('status_code')
                    if status_code:
                        message = _('HTTP %s: %s') % (status_code, message)
                    fail(message)
                    continue

            vals = {
                'bird_contact_id': str(bird_id),
                'bird_sync_status': 'synced',
                'bird_synced_at': fields.Datetime.now(),
                'bird_sync_error': False,
            }
            if rec.whatsapp_number != phone:
                vals['whatsapp_number'] = phone
                vals['normalized_number'] = rec._normalize_phone(phone)
            rec.with_context(skip_bird_contact_sync=True).sudo().write(vals)
        return True

    def action_sync_bird_contact(self):
        self.ensure_one()
        self._sync_bird_contact_identity(raise_on_error=True)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

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
            'whatsapp_number': self._format_phone_e164(number, organization=organization),
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
