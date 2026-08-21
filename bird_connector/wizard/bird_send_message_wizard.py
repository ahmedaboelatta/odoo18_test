import json
import re

from odoo import api, fields, models
from odoo.exceptions import UserError


class BirdSendMessageWizard(models.TransientModel):
    _name = "bird.send.message.wizard"
    _description = "Send Bird Message"

    message_type = fields.Selection([
        ("template", "WhatsApp Template"),
        ("text", "Text Message"),
        ("image", "Image Message"),
        ("file", "File Message"),
    ], string="Message Type", default="template", required=True)
    organization_id = fields.Many2one("bird.organization", string="Organization", required=True)
    workspace_id = fields.Many2one(
        "bird.workspace", string="Workspace", required=True,
        domain="[('organization_id', '=', organization_id)]",
    )
    channel_id = fields.Many2one(
        "bird.channel", string="Channel", required=False,
        domain="[('workspace_id', '=', workspace_id), ('channel_type', '=', 'whatsapp'), ('state', '=', 'connected')]",
    )
    template_id = fields.Many2one(
        "bird.template", string="Template",
        domain="[('workspace_id', '=', workspace_id)]",
    )
    bulk_mode = fields.Boolean(string="Bulk Send", default=False, readonly=True)
    contact_ids = fields.Many2many("bird.contact", string="Recipients", readonly=True)
    recipient_count = fields.Integer(string="Recipients", compute="_compute_recipient_count")
    recipient_summary = fields.Char(string="Recipient Summary", compute="_compute_recipient_count")
    bulk_schedule_at = fields.Datetime(
        string='Schedule At',
        help='Leave empty to start the campaign as soon as the scheduler runs.'
    )
    bulk_batch_size = fields.Integer(string='Batch Size', default=10)
    bulk_interval_minutes = fields.Integer(string='Batch Interval (Minutes)', default=1)
    bulk_max_retries = fields.Integer(string='Max Retries', default=2)

    receiver_mobile = fields.Char(
        string="Receiver Mobile", required=False,
        help="Use international format, e.g. +9665XXXXXXXX.",
    )
    locale = fields.Selection([("en", "English"), ("ar", "Arabic")], string="Locale", default="en")
    reference = fields.Char(string="Reference", help="Optional internal reference sent to Bird when supported.")

    message_text = fields.Text(string="Message Text")
    media_url = fields.Char(string="Public Media URL", help="Public HTTPS URL accessible by Bird.")
    filename = fields.Char(string="Filename", help="Optional filename for file messages, e.g. invoice.pdf")
    caption = fields.Text(string="Caption")

    parameter_ids = fields.One2many("bird.send.message.parameter", "wizard_id", string="Template Variables")
    preview_text = fields.Text(string="Template Preview", readonly=True)
    preview_header_image = fields.Binary(related="template_id.preview_header_image", readonly=True)
    preview_header_text = fields.Char(related="template_id.preview_header_text", readonly=True)
    preview_footer_text = fields.Char(related="template_id.preview_footer_text", readonly=True)
    preview_button_1 = fields.Char(related="template_id.preview_button_1", readonly=True)
    preview_button_2 = fields.Char(related="template_id.preview_button_2", readonly=True)
    preview_button_3 = fields.Char(related="template_id.preview_button_3", readonly=True)

    @api.depends('contact_ids')
    def _compute_recipient_count(self):
        for rec in self:
            contacts = rec.contact_ids
            rec.recipient_count = len(contacts)
            names = contacts[:5].mapped('display_name')
            summary = ', '.join(names)
            if len(contacts) > 5:
                summary = '%s + %s more' % (summary, len(contacts) - 5)
            rec.recipient_summary = summary or False

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if self.env.context.get("active_model") == "bird.contact" or self.env.context.get("bird_bulk_mode"):
            contacts = self.env["bird.contact"].browse(self.env.context.get("active_ids") or []).exists()
            vals["bulk_mode"] = True
            vals["contact_ids"] = [(6, 0, contacts.ids)]
            vals["message_type"] = "template"
            if contacts:
                vals["organization_id"] = contacts[0].organization_id.id
                vals["workspace_id"] = contacts[0].workspace_id.id
            return vals
        template_id = self.env.context.get("default_template_id") or self.env.context.get("active_id")
        if template_id and self.env.context.get("active_model") == "bird.template":
            template = self.env["bird.template"].browse(template_id).exists()
            if template:
                vals.update({
                    "message_type": "template",
                    "template_id": template.id,
                    "workspace_id": template.workspace_id.id,
                    "organization_id": template.organization_id.id,
                    "locale": template.locale or "en",
                    "preview_text": template.preview_body_text or template.body or "",
                })
                channel = template.channel_id or self.env["bird.channel"].search([
                    ("workspace_id", "=", template.workspace_id.id),
                    ("channel_type", "=", "whatsapp"),
                    ("state", "=", "connected"),
                ], limit=1)
                if channel:
                    vals["channel_id"] = channel.id
                commands = self._build_parameter_commands(template)
                if commands:
                    vals["parameter_ids"] = commands
        else:
            organization = self.env["bird.organization"].search([], limit=1)
            if organization:
                vals["organization_id"] = organization.id
                workspace = self.env["bird.workspace"].search([("organization_id", "=", organization.id)], limit=1)
                if workspace:
                    vals["workspace_id"] = workspace.id
                    channel = self.env["bird.channel"].search([
                        ("workspace_id", "=", workspace.id),
                        ("channel_type", "=", "whatsapp"),
                        ("state", "=", "connected"),
                    ], limit=1)
                    if channel:
                        vals["channel_id"] = channel.id
        return vals

    @api.model
    def _extract_variable_keys(self, template):
        keys = []
        for line in getattr(template, "variable_line_ids", self.env["bird.template.variable"]):
            key = line.key or line._get_variable_key()
            if key and key not in keys:
                keys.append(key)
        def add(value):
            value = str(value or "").strip()
            if value and value not in keys:
                keys.append(value)
        raw = template.variables or ""
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, dict) and value.get("key"):
                            add(value.get("key"))
                        else:
                            add(key)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            add(item.get("key") or item.get("name") or item.get("variable"))
                        elif isinstance(item, str):
                            add(item)
            except Exception:
                pass
        searchable = "\n".join(filter(None, [
            template.preview_body_text, template.body, template.header_text,
            template.footer_text, template.platform_content, template.generic_content,
        ]))
        for match in re.findall(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", searchable):
            add(match)
        return keys

    @api.model
    def _build_parameter_commands(self, template):
        mapped = {}
        for line in getattr(template, "variable_line_ids", self.env["bird.template.variable"]):
            key = line.key or line._get_variable_key()
            if not key:
                continue
            value = ""
            if line.variable_type == "user_name":
                value = self.env.user.name or ""
            elif line.variable_type == "user_mobile":
                value = self.env.user.partner_id.mobile or self.env.user.partner_id.phone or ""
            elif line.variable_type == "portal_link":
                value = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
            elif line.variable_type == "free_text":
                value = line.sample_value or ""
            mapped[key] = value
        return [(0, 0, {"key": key, "parameter_type": "string", "value": mapped.get(key, "")}) for key in self._extract_variable_keys(template)]

    @api.onchange("organization_id")
    def _onchange_organization_id(self):
        if self.workspace_id.organization_id != self.organization_id:
            self.workspace_id = False
            self.channel_id = False
            self.template_id = False
            self.parameter_ids = [(5, 0, 0)]

    @api.onchange("workspace_id")
    def _onchange_workspace_id(self):
        if self.channel_id.workspace_id != self.workspace_id:
            self.channel_id = False
        if self.template_id.workspace_id != self.workspace_id:
            self.template_id = False
            self.parameter_ids = [(5, 0, 0)]

    @api.onchange("message_type")
    def _onchange_message_type(self):
        if self.message_type != "template":
            self.template_id = False
            self.parameter_ids = [(5, 0, 0)]
            self.preview_text = False

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if not self.template_id:
            self.parameter_ids = [(5, 0, 0)]
            self.preview_text = False
            return
        self.message_type = "template"
        self.workspace_id = self.template_id.workspace_id
        self.organization_id = self.template_id.organization_id
        self.locale = self.template_id.locale or "en"
        self.channel_id = self.template_id.channel_id
        self.preview_text = self.template_id.preview_body_text or self.template_id.body or ""
        self.parameter_ids = [(5, 0, 0)] + self._build_parameter_commands(self.template_id)

    def action_send(self):
        self.ensure_one()
        engine = self.env["bird.message.engine"]
        if self.message_type != "template":
            raise UserError("This wizard is intended for Approved WhatsApp templates.")
        if not self.template_id:
            raise UserError("Please select a template.")
        if self.template_id.status != "active":
            raise UserError("Only Approved WhatsApp templates can be sent.")
        if not self.template_id.channel_id:
            raise UserError("This template has no WhatsApp Channel. Sync/fix the template first.")

        # Channel ownership is immutable for template sending: always use the
        # channel the template belongs to, never a user-selected alternate channel.
        channel = self.template_id.channel_id
        self.channel_id = channel
        self.workspace_id = self.template_id.workspace_id
        self.organization_id = self.template_id.organization_id

        missing = self.parameter_ids.filtered(lambda line: not line.value and line.required)
        if missing:
            raise UserError("Please fill all required template variables: %s" % ", ".join(missing.mapped("key")))
        parameters = [{
            "type": line.parameter_type or "string",
            "key": line.key,
            "value": line.value or "",
        } for line in self.parameter_ids if line.key]

        if self.bulk_mode or self.contact_ids:
            contacts = self.contact_ids.exists()
            if not contacts:
                raise UserError("Select at least one Bird contact.")

            # A single recipient is not a bulk campaign. Send it immediately,
            # while still using the same Bird identity sync + delivery tracking.
            if len(contacts) == 1:
                contact = contacts[0].sudo()
                if not contact.bird_contact_id or contact.bird_sync_status != 'synced':
                    contact._sync_bird_contact_identity(raise_on_error=True)
                log = engine.send_whatsapp_template(
                    channel=channel,
                    receiver=contact.whatsapp_number,
                    template=self.template_id,
                    parameters=parameters,
                    locale=self.locale or self.template_id.locale or 'en',
                    reference=self.reference,
                )
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Bird Message' if log.status != 'failed' else 'Bird Message Failed',
                    'res_model': 'bird.message.log',
                    'res_id': log.id,
                    'view_mode': 'form',
                    'target': 'current',
                }

            # Two or more recipients use the queued campaign path. Each line is
            # preflighted (number validation + Bird Contact sync) before sending.
            if (self.bulk_batch_size or 0) < 1:
                raise UserError('Batch Size must be at least 1.')
            if (self.bulk_interval_minutes or 0) < 0:
                raise UserError('Batch Interval cannot be negative.')
            if (self.bulk_max_retries or 0) < 0:
                raise UserError('Max Retries cannot be negative.')
            batch = self.env['bird.bulk.send'].create({
                'organization_id': self.template_id.organization_id.id,
                'workspace_id': self.template_id.workspace_id.id,
                'channel_id': channel.id,
                'template_id': self.template_id.id,
                'locale': self.locale or self.template_id.locale or 'en',
                'reference': self.reference,
                'parameter_json': json.dumps(parameters, ensure_ascii=False),
                'scheduled_at': self.bulk_schedule_at or False,
                'batch_size': self.bulk_batch_size or 10,
                'batch_interval_minutes': self.bulk_interval_minutes if self.bulk_interval_minutes is not None else 1,
                'max_retries': self.bulk_max_retries if self.bulk_max_retries is not None else 2,
                'line_ids': [(0, 0, {'contact_id': contact.id}) for contact in contacts],
            })
            return {
                'type': 'ir.actions.act_window',
                'name': 'WhatsApp Bulk Send',
                'res_model': 'bird.bulk.send',
                'res_id': batch.id,
                'view_mode': 'form',
                'target': 'current',
            }

        if not self.receiver_mobile:
            raise UserError("Receiver Mobile is required.")
        log = engine.send_whatsapp_template(
            channel=channel, receiver=self.receiver_mobile, template=self.template_id,
            parameters=parameters, locale=self.locale, reference=self.reference,
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Bird Message" if log.status != "failed" else "Bird Message Failed",
            "res_model": "bird.message.log", "res_id": log.id, "view_mode": "form", "target": "current",
        }



class BirdSendMessageParameter(models.TransientModel):
    _name = "bird.send.message.parameter"
    _description = "Bird Send Message Parameter"
    _order = "id"

    wizard_id = fields.Many2one("bird.send.message.wizard", string="Wizard", required=True, ondelete="cascade")
    key = fields.Char(string="Variable", required=True, readonly=True)
    parameter_type = fields.Selection([("string", "String")], string="Type", default="string", required=True)
    value = fields.Char(string="Value")
    required = fields.Boolean(string="Required", default=True)
