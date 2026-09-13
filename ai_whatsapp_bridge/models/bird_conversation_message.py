from odoo import fields, models


class BirdConversationMessage(models.Model):
    _inherit = "bird.conversation.message"

    message_type = fields.Selection(selection_add=[("location", "Location")], ondelete={"location": "set default"})
