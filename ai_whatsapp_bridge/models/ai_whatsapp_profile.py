import json
import logging
import re

import requests

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class AiWhatsappProfile(models.Model):
    _name = "ai.whatsapp.profile"
    _description = "AI WhatsApp Brand Profile"
    _order = "name, id"

    name = fields.Char(string="Brand Name", required=True, index=True)
    code = fields.Char(string="Brand Code", required=True, index=True)
    active = fields.Boolean(default=True)
    enabled = fields.Boolean(string="Enable AI Integration", default=False)
    channel_id = fields.Many2one(
        "bird.channel",
        string="Bird WhatsApp Channel",
        required=True,
        ondelete="restrict",
        domain="[('channel_type', '=', 'whatsapp')]",
    )
    n8n_webhook_url = fields.Char(string="n8n Webhook URL", required=True)
    secret_header_name = fields.Char(
        string="Secret Header Name",
        default="X-AI-Bridge-Secret",
        required=True,
    )
    n8n_secret = fields.Char(
        string="Secret Header Value",
        groups="bird_connector.group_bird_administrator,base.group_system",
    )
    request_timeout = fields.Integer(string="Request Timeout (Seconds)", default=10, required=True)
    auto_send_reply = fields.Boolean(string="Auto-send AI Reply", default=False)
    log_ids = fields.One2many("ai.whatsapp.forward.log", "profile_id", string="Forwarding Logs")
    log_count = fields.Integer(compute="_compute_log_count")

    _sql_constraints = [
        ("ai_whatsapp_profile_code_unique", "unique(code)", "Brand Code must be unique."),
        ("ai_whatsapp_profile_channel_unique", "unique(channel_id)", "A Bird channel can only belong to one AI profile."),
        ("ai_whatsapp_profile_timeout_positive", "CHECK(request_timeout > 0)", "Request timeout must be greater than zero."),
    ]

    @api.depends("log_ids")
    def _compute_log_count(self):
        for profile in self:
            profile.log_count = self.env["ai.whatsapp.forward.log"].search_count([
                ("profile_id", "=", profile.id)
            ])

    @api.constrains("channel_id")
    def _check_whatsapp_channel(self):
        for profile in self:
            if profile.channel_id and profile.channel_id.channel_type != "whatsapp":
                raise ValidationError(_("The selected Bird channel must be a WhatsApp channel."))

    @api.constrains("n8n_webhook_url")
    def _check_webhook_url(self):
        for profile in self:
            url = (profile.n8n_webhook_url or "").strip().lower()
            if url and not (url.startswith("https://") or url.startswith("http://")):
                raise ValidationError(_("The n8n webhook URL must start with http:// or https://."))

    @api.constrains("enabled", "n8n_secret", "secret_header_name")
    def _check_callback_credentials(self):
        for profile in self:
            header_name = (profile.secret_header_name or "").strip()
            if header_name and not re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", header_name):
                raise ValidationError(_("Secret Header Name must be a valid HTTP header name."))
            if profile.enabled and (not header_name or not profile.n8n_secret):
                raise ValidationError(_("Configure the callback secret header name and value before enabling AI integration."))

    def action_view_logs(self):
        self.ensure_one()
        action = self.env.ref("ai_whatsapp_bridge.action_ai_whatsapp_forward_log").read()[0]
        action["domain"] = [("profile_id", "=", self.id)]
        action["context"] = {"default_profile_id": self.id}
        return action

    def _send_to_n8n(self, message, forward_log):
        self.ensure_one()
        payload = {
            "message_id": message.bird_message_id or "",
            "direction": "incoming",
            "brand_code": self.code or "",
            "brand_name": self.name or "",
            "channel_name": message.channel_id.name or "",
            "channel_phone": message.channel_id.connected_account or "",
            "customer_phone": message.contact_id.whatsapp_number or "",
            "message_type": "text",
            "text": message.body or "",
            "conversation_id": str(message.conversation_id.id),
        }
        headers = {"Content-Type": "application/json"}
        if self.n8n_secret:
            headers[(self.secret_header_name or "X-AI-Bridge-Secret").strip()] = self.n8n_secret

        forward_log.sudo().write({
            "status": "sending",
            "attempt_count": forward_log.attempt_count + 1,
            "request_payload": json.dumps(payload, ensure_ascii=False),
            "last_attempt_at": fields.Datetime.now(),
        })
        response = requests.post(
            self.n8n_webhook_url.strip(),
            json=payload,
            headers=headers,
            timeout=max(1, int(self.request_timeout or 10)),
        )
        response_text = (response.text or "")[:20000]
        if not response.ok:
            raise requests.HTTPError("n8n returned HTTP %s" % response.status_code, response=response)

        forward_log.sudo().write({
            "status": "forwarded",
            "http_status": response.status_code,
            "response_body": response_text,
            "forwarded_at": fields.Datetime.now(),
            "error_message": False,
        })
        return True
