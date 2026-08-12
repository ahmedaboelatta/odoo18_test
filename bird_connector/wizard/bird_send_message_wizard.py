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
        "bird.channel", string="Channel", required=True,
        domain="[('workspace_id', '=', workspace_id), ('channel_type', '=', 'whatsapp'), ('state', '=', 'connected')]",
    )
    template_id = fields.Many2one(
        "bird.template", string="Template",
        domain="[('workspace_id', '=', workspace_id)]",
    )
    receiver_mobile = fields.Char(
        string="Receiver Mobile", required=True,
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

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
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
                channel = self.env["bird.channel"].search([
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
        return [(0, 0, {"key": key, "parameter_type": "string", "value": ""}) for key in self._extract_variable_keys(template)]

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
        self.preview_text = self.template_id.preview_body_text or self.template_id.body or ""
        self.parameter_ids = [(5, 0, 0)] + self._build_parameter_commands(self.template_id)

    def action_send(self):
        self.ensure_one()
        engine = self.env["bird.message.engine"]
        if self.message_type == "template":
            if not self.template_id:
                raise UserError("Please select a template.")
            missing = self.parameter_ids.filtered(lambda line: not line.value and line.required)
            if missing:
                raise UserError("Please fill all required template variables: %s" % ", ".join(missing.mapped("key")))
            parameters = [{
                "type": line.parameter_type or "string",
                "key": line.key,
                "value": line.value or "",
            } for line in self.parameter_ids if line.key]
            log = engine.send_whatsapp_template(
                channel=self.channel_id, receiver=self.receiver_mobile, template=self.template_id,
                parameters=parameters, locale=self.locale, reference=self.reference,
            )
        elif self.message_type == "text":
            log = engine.send_whatsapp_text(
                channel=self.channel_id, receiver=self.receiver_mobile,
                text=self.message_text, reference=self.reference,
            )
        elif self.message_type == "image":
            log = engine.send_whatsapp_image(
                channel=self.channel_id, receiver=self.receiver_mobile,
                media_url=self.media_url, caption=self.caption, reference=self.reference,
            )
        elif self.message_type == "file":
            log = engine.send_whatsapp_file(
                channel=self.channel_id, receiver=self.receiver_mobile,
                media_url=self.media_url, filename=self.filename,
                caption=self.caption, reference=self.reference,
            )
        else:
            raise UserError("Unsupported message type.")

        return {
            "type": "ir.actions.act_window",
            "name": "Bird Message" if log.status != "failed" else "Bird Message Failed",
            "res_model": "bird.message.log",
            "res_id": log.id,
            "view_mode": "form",
            "target": "current",
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
