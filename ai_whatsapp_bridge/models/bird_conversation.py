import logging

from psycopg2 import IntegrityError

from odoo import api, fields, models


_logger = logging.getLogger(__name__)


class BirdConversation(models.Model):
    _inherit = "bird.conversation"

    @api.model
    def _record_inbound(self, contact, channel, payload, message_id=False, event_time=None, status=False):
        message = super()._record_inbound(
            contact, channel, payload, message_id=message_id, event_time=event_time, status=status
        )
        try:
            self._ai_bridge_forward_message(message)
        except Exception:
            # AI integration is best-effort and must never affect Bird webhook handling.
            _logger.exception("Unexpected AI bridge failure after storing Bird message %s", message_id)
        return message

    @api.model
    def _ai_bridge_forward_message(self, message):
        if (
            not message
            or not message.exists()
            or message.direction != "inbound"
            or message.message_type != "text"
            or not message.bird_message_id
            or not (message.body or "").strip()
        ):
            return False

        global_enabled = self.env["ir.config_parameter"].sudo().get_param(
            "ai_whatsapp_bridge.enabled", "True"
        )
        if str(global_enabled).strip().lower() not in ("1", "true", "yes", "on"):
            return False

        profile = self.env["ai.whatsapp.profile"].sudo().search([
            ("active", "=", True),
            ("enabled", "=", True),
            ("channel_id", "=", message.channel_id.id),
        ], limit=1)
        if not profile:
            return False

        ForwardLog = self.env["ai.whatsapp.forward.log"].sudo()
        if ForwardLog.search_count([("bird_message_id", "=", message.bird_message_id)]):
            _logger.info("Skipping duplicate AI forwarding for Bird message %s", message.bird_message_id)
            return False

        try:
            with self.env.cr.savepoint():
                forward_log = ForwardLog.create({
                    "profile_id": profile.id,
                    "message_id": message.id,
                    "bird_message_id": message.bird_message_id,
                })
        except IntegrityError:
            _logger.info("Concurrent duplicate AI forwarding skipped for Bird message %s", message.bird_message_id)
            return False

        try:
            profile._send_to_n8n(message, forward_log)
        except Exception as exc:
            http_status = getattr(getattr(exc, "response", None), "status_code", 0) or 0
            response_text = getattr(getattr(exc, "response", None), "text", "") or ""
            forward_log.sudo().write({
                "status": "failed",
                "http_status": http_status,
                "response_body": response_text[:20000],
                "error_message": str(exc)[:4000],
                "last_attempt_at": fields.Datetime.now(),
            })
            _logger.exception("n8n forwarding failed for Bird message %s", message.bird_message_id)
        return True
