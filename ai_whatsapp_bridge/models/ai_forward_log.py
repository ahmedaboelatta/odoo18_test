import json
import logging

from odoo import fields, models


_logger = logging.getLogger(__name__)


class AiWhatsappForwardLog(models.Model):
    _name = "ai.whatsapp.forward.log"
    _description = "AI WhatsApp Forwarding Log"
    _order = "create_date desc, id desc"

    profile_id = fields.Many2one("ai.whatsapp.profile", required=True, ondelete="restrict", index=True)
    message_id = fields.Many2one("bird.conversation.message", required=True, ondelete="cascade", index=True)
    bird_message_id = fields.Char(required=True, index=True, readonly=True)
    conversation_id = fields.Many2one("bird.conversation", related="message_id.conversation_id", store=True, index=True)
    channel_id = fields.Many2one("bird.channel", related="message_id.channel_id", store=True, index=True)
    status = fields.Selection([
        ("pending", "Pending"),
        ("sending", "Sending"),
        ("forwarded", "Forwarded"),
        ("failed", "Failed"),
        ("reply_sent", "Reply Sent"),
        ("reply_failed", "Reply Failed"),
    ], default="pending", required=True, index=True, readonly=True)
    attempt_count = fields.Integer(default=0, readonly=True)
    last_attempt_at = fields.Datetime(readonly=True)
    forwarded_at = fields.Datetime(readonly=True)
    replied_at = fields.Datetime(readonly=True)
    http_status = fields.Integer(readonly=True)
    request_payload = fields.Text(readonly=True)
    response_body = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)
    reply_text = fields.Text(readonly=True)
    outbound_message_id = fields.Many2one("bird.conversation.message", readonly=True, ondelete="set null")
    bird_message_log_id = fields.Many2one("bird.message.log", readonly=True, ondelete="set null")
    outbound_bird_message_id = fields.Char(string="Bird Outbound Message ID", readonly=True, index=True)
    callback_state = fields.Selection([
        ("waiting", "Waiting"),
        ("processing", "Processing"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ], default="waiting", required=True, readonly=True, index=True)
    callback_received_at = fields.Datetime(readonly=True)
    callback_metadata = fields.Text(readonly=True)

    _sql_constraints = [
        ("ai_forward_bird_message_unique", "unique(bird_message_id)", "This Bird message has already been processed by the AI bridge."),
    ]

    def _claim_callback(self, metadata):
        """Atomically claim one callback; terminal/processing rows cannot resend."""
        self.ensure_one()
        self.flush_recordset(["callback_state"])
        self.env.cr.execute(
            """
                UPDATE ai_whatsapp_forward_log
                   SET callback_state = 'processing',
                       callback_received_at = %s,
                       callback_metadata = %s,
                       write_date = %s,
                       write_uid = %s
                 WHERE id = %s
                   AND callback_state = 'waiting'
             RETURNING id
            """,
            (
                fields.Datetime.now(),
                json.dumps(metadata, ensure_ascii=False),
                fields.Datetime.now(),
                self.env.uid,
                self.id,
            ),
        )
        claimed = bool(self.env.cr.fetchone())
        self.invalidate_recordset(["callback_state", "callback_received_at", "callback_metadata"])
        return claimed

    def process_callback_reply(self, reply_text, metadata):
        """Send a claimed AI reply through Bird and mirror it in the same inbox."""
        self.ensure_one()
        if not self._claim_callback(metadata):
            return {"ok": False, "code": "duplicate_reply", "http_status": 409}

        incoming_message = self.message_id.sudo()
        conversation = incoming_message.conversation_id.sudo()
        bird_log = self.env["bird.message.log"]
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
            conversation.write({
                "last_message": reply_text,
                "last_message_at": bird_log.send_date or now,
                "state": "open",
            })
            conversation.contact_id.sudo().write({
                "last_message": reply_text,
                "last_message_at": bird_log.send_date or now,
                "last_activity_at": bird_log.send_date or now,
            })
            send_failed = bird_log.status == "failed"
            error_message = (bird_log.error_message or "Bird rejected the AI reply") if send_failed else False
            self.sudo().write({
                "status": "reply_failed" if send_failed else "reply_sent",
                "callback_state": "failed" if send_failed else "sent",
                "reply_text": reply_text,
                "outbound_message_id": outgoing.id,
                "outbound_bird_message_id": bird_log.bird_message_id or False,
                "bird_message_log_id": bird_log.id,
                "replied_at": False if send_failed else fields.Datetime.now(),
                "error_message": error_message,
            })
            conversation._notify_inbox_update("ai_reply")
            if send_failed:
                return {"ok": False, "code": "bird_send_failed", "message": error_message, "http_status": 502}
            return {
                "ok": True,
                "code": "reply_sent",
                "http_status": 200,
                "bird_message_id": bird_log.bird_message_id or False,
            }
        except Exception as exc:
            _logger.exception("AI callback reply failed for Bird message %s", incoming_message.bird_message_id)
            vals = {
                "status": "reply_failed",
                "callback_state": "failed",
                "reply_text": reply_text,
                "error_message": str(exc)[:4000],
            }
            if bird_log:
                vals.update({
                    "bird_message_log_id": bird_log.id,
                    "outbound_bird_message_id": bird_log.bird_message_id or False,
                })
            self.sudo().write(vals)
            return {"ok": False, "code": "bird_send_failed", "message": "Unable to send the AI reply.", "http_status": 502}
