import json
import logging

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

    def action_view_logs(self):
        self.ensure_one()
        action = self.env.ref("ai_whatsapp_bridge.action_ai_whatsapp_forward_log").read()[0]
        action["domain"] = [("profile_id", "=", self.id)]
        action["context"] = {"default_profile_id": self.id}
        return action

    @api.model
    def _extract_reply_text(self, response_data):
        """Accept a small set of explicit n8n reply contracts."""
        if not isinstance(response_data, dict):
            return False
        for key in ("reply_text", "reply", "ai_reply", "output"):
            value = response_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("data", "output", "result"):
            nested = response_data.get(key)
            if isinstance(nested, dict):
                reply = self._extract_reply_text(nested)
                if reply:
                    return reply
        return False

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

        try:
            response_data = response.json() if response_text else {}
        except ValueError:
            response_data = {}
        forward_log.sudo().write({
            "status": "forwarded",
            "http_status": response.status_code,
            "response_body": response_text,
            "forwarded_at": fields.Datetime.now(),
            "error_message": False,
        })

        reply_text = self._extract_reply_text(response_data)
        if self.auto_send_reply and reply_text:
            self._send_ai_reply(message, forward_log, reply_text)
        elif self.auto_send_reply:
            _logger.info("n8n returned no AI reply for Bird message %s", message.bird_message_id)
        return True

    def _send_ai_reply(self, incoming_message, forward_log, reply_text):
        self.ensure_one()
        conversation = incoming_message.conversation_id
        try:
            bird_log = self.env["bird.message.engine"].sudo().send_whatsapp_text(
                conversation.channel_id,
                conversation.contact_id.whatsapp_number,
                reply_text,
                reference="ai-bridge:%s" % incoming_message.bird_message_id,
            )
            now = fields.Datetime.now()
            outgoing = self.env["bird.conversation.message"].sudo().create({
                "conversation_id": conversation.id,
                "direction": "outbound",
                "message_type": "text",
                "body": reply_text,
                "bird_message_id": bird_log.bird_message_id,
                "bird_status": bird_log.bird_status or bird_log.status,
                "message_at": bird_log.send_date or now,
                "message_log_id": bird_log.id,
            })
            conversation.sudo().write({
                "last_message": reply_text,
                "last_message_at": bird_log.send_date or now,
                "state": "open",
            })
            conversation.contact_id.sudo().write({
                "last_message": reply_text,
                "last_message_at": bird_log.send_date or now,
                "last_activity_at": bird_log.send_date or now,
            })
            reply_failed = bird_log.status == "failed"
            forward_log.sudo().write({
                "status": "reply_failed" if reply_failed else "reply_sent",
                "reply_text": reply_text,
                "outbound_message_id": outgoing.id,
                "bird_message_log_id": bird_log.id,
                "replied_at": False if reply_failed else fields.Datetime.now(),
                "error_message": (bird_log.error_message or "Bird rejected the AI reply") if reply_failed else False,
            })
            conversation._notify_inbox_update("ai_reply")
        except Exception as exc:
            _logger.exception("AI reply failed for Bird message %s", incoming_message.bird_message_id)
            forward_log.sudo().write({
                "status": "reply_failed",
                "reply_text": reply_text,
                "error_message": str(exc)[:4000],
            })
        return True
