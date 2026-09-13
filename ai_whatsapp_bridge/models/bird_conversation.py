import logging
import json

from psycopg2 import IntegrityError

from odoo import api, fields, models


_logger = logging.getLogger(__name__)


class BirdConversation(models.Model):
    _inherit = "bird.conversation"

    @api.model
    def _extract_message_content(self, payload):
        content = super()._extract_message_content(payload)
        body = payload.get("body") if isinstance(payload, dict) else None
        if isinstance(body, dict) and body.get("type") == "location":
            return ("location", "LOCATION", False, False, False, False)
        return content

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
            or not message.bird_message_id
        ):
            _logger.debug("AI forward skipped: absent or non-inbound Bird message")
            return False

        global_enabled = self.env["ir.config_parameter"].sudo().get_param(
            "ai_whatsapp_bridge.enabled", "True"
        )
        if str(global_enabled).strip().lower() not in ("1", "true", "yes", "on"):
            _logger.info("AI forward skipped for %s: global integration disabled", message.bird_message_id)
            return False

        profile = self.env["ai.whatsapp.profile"].sudo().search([
            ("active", "=", True),
            ("enabled", "=", True),
            ("channel_id", "=", message.channel_id.id),
        ], limit=1)
        if not profile:
            _logger.info("AI forward skipped for %s: no enabled profile for channel %s", message.bird_message_id, message.channel_id.id)
            return False
        if not profile.auto_send_reply:
            _logger.info("AI forward skipped for %s: auto-send disabled on profile %s", message.bird_message_id, profile.id)
            return False

        try:
            raw = json.loads(message.raw_payload or "{}")
        except (ValueError, TypeError):
            raw = {}
        body = raw.get("body") if isinstance(raw, dict) else None
        raw_type = str(body.get("type") or "").lower() if isinstance(body, dict) else ""
        detected_type = raw_type or message.message_type

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
                    "message_type": detected_type,
                    "customer_phone": message.contact_id.whatsapp_number or False,
                })
        except IntegrityError:
            _logger.info("Concurrent duplicate AI forwarding skipped for Bird message %s", message.bird_message_id)
            return False

        _logger.info("AI inbound %s type=%s profile=%s channel=%s", message.bird_message_id, detected_type, profile.id, message.channel_id.id)
        if detected_type not in ("text", "location"):
            forward_log.write({"status": "skipped", "error_message": "Unsupported inbound message type: %s" % detected_type})
            _logger.info("AI forward skipped for %s: unsupported type %s", message.bird_message_id, detected_type)
            return False

        try:
            profile._build_ai_forward_payload(message)
        except ValueError as exc:
            forward_log.write({"status": "skipped", "error_message": str(exc)})
            _logger.info("AI forward skipped for %s: %s", message.bird_message_id, exc)
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
