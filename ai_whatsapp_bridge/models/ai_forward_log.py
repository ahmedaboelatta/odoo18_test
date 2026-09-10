from odoo import fields, models


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

    _sql_constraints = [
        ("ai_forward_bird_message_unique", "unique(bird_message_id)", "This Bird message has already been processed by the AI bridge."),
    ]
