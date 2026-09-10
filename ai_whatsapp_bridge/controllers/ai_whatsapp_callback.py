import hmac
import json
import logging

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class AiWhatsappCallbackController(http.Controller):

    @staticmethod
    def _json_response(payload, status=200):
        return request.make_json_response(payload, status=status)

    @http.route(
        "/ai_whatsapp/reply",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def ai_whatsapp_reply(self, **kwargs):
        if (request.httprequest.mimetype or "").lower() != "application/json":
            return self._json_response({
                "ok": False,
                "code": "json_required",
                "message": "Content-Type must be application/json.",
            }, status=415)

        try:
            payload = json.loads((request.httprequest.get_data(cache=True) or b"").decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return self._json_response({
                "ok": False,
                "code": "invalid_json",
                "message": "Request body must contain a valid JSON object.",
            }, status=400)
        if not isinstance(payload, dict):
            return self._json_response({
                "ok": False,
                "code": "invalid_payload",
                "message": "Request body must be a JSON object.",
            }, status=400)

        message_id = str(payload.get("message_id") or "").strip()
        conversation_value = payload.get("conversation_id")
        customer_phone = str(payload.get("customer_phone") or "").strip()
        reply_text = payload.get("reply_text")
        reply_text = reply_text.strip() if isinstance(reply_text, str) else ""
        if not message_id or not conversation_value or not customer_phone or not reply_text:
            return self._json_response({
                "ok": False,
                "code": "missing_fields",
                "message": "message_id, conversation_id, customer_phone, and non-empty reply_text are required.",
            }, status=400)
        try:
            conversation_id = int(conversation_value)
        except (TypeError, ValueError):
            return self._json_response({
                "ok": False,
                "code": "invalid_conversation_id",
                "message": "conversation_id must be an integer Odoo conversation ID.",
            }, status=400)

        conversation = request.env["bird.conversation"].sudo().browse(conversation_id).exists()
        if not conversation:
            return self._json_response({
                "ok": False,
                "code": "conversation_not_found",
                "message": "Bird conversation was not found.",
            }, status=404)
        profile = request.env["ai.whatsapp.profile"].sudo().search([
            ("active", "=", True),
            ("enabled", "=", True),
            ("channel_id", "=", conversation.channel_id.id),
        ], limit=1)
        if not profile:
            return self._json_response({
                "ok": False,
                "code": "profile_not_found",
                "message": "No enabled AI profile is configured for this conversation channel.",
            }, status=404)

        expected_secret = profile.n8n_secret or ""
        provided_secret = request.httprequest.headers.get(profile.secret_header_name or "") or ""
        if not expected_secret or not hmac.compare_digest(str(provided_secret), str(expected_secret)):
            _logger.warning("Rejected AI callback authentication for conversation %s", conversation.id)
            return self._json_response({
                "ok": False,
                "code": "unauthorized",
                "message": "Invalid callback credentials.",
            }, status=401)
        if not profile.auto_send_reply:
            return self._json_response({
                "ok": False,
                "code": "auto_reply_disabled",
                "message": "Auto-send AI Reply is disabled for this brand profile.",
            }, status=403)

        forward_log = request.env["ai.whatsapp.forward.log"].sudo().search([
            ("profile_id", "=", profile.id),
            ("bird_message_id", "=", message_id),
            ("conversation_id", "=", conversation.id),
        ], limit=1)
        if not forward_log or forward_log.message_id.direction != "inbound":
            return self._json_response({
                "ok": False,
                "code": "incoming_message_not_found",
                "message": "The forwarded incoming Bird message was not found in this conversation.",
            }, status=404)

        normalized_callback_phone = "".join(ch for ch in customer_phone if ch.isdigit())
        normalized_contact_phone = "".join(
            ch for ch in (conversation.contact_id.whatsapp_number or "") if ch.isdigit()
        )
        if not normalized_callback_phone or normalized_callback_phone != normalized_contact_phone:
            return self._json_response({
                "ok": False,
                "code": "customer_mismatch",
                "message": "customer_phone does not match the conversation contact.",
            }, status=409)

        metadata = {
            "message_id": message_id,
            "conversation_id": str(conversation.id),
            "customer_phone": customer_phone,
            "reply_text_length": len(reply_text),
            "payload_keys": sorted(
                key for key in ("message_id", "conversation_id", "customer_phone", "reply_text")
                if key in payload
            ),
        }
        _logger.info(
            "Accepted n8n AI callback metadata: message_id=%s conversation_id=%s reply_length=%s",
            message_id, conversation.id, len(reply_text),
        )
        result = forward_log.process_callback_reply(reply_text, metadata)
        status = result.pop("http_status", 200)
        if result.get("ok"):
            result["message"] = "AI reply sent successfully."
        elif result.get("code") == "duplicate_reply":
            result["message"] = "A callback for this incoming message was already processed."
        return self._json_response(result, status=status)
