from odoo import api, fields, models


class BirdQuickReply(models.Model):
    _name = "bird.quick.reply"
    _description = "Bird WhatsApp Quick Reply"
    _order = "sequence, name, id"

    name = fields.Char(required=True, index=True)
    shortcut = fields.Char(
        string="Shortcut",
        help="Optional short code shown in the inbox, e.g. hours or delivery.",
        index=True,
    )
    message = fields.Text(required=True)
    channel_id = fields.Many2one(
        "bird.channel",
        string="WhatsApp Channel",
        domain=[("channel_type", "=", "whatsapp")],
        ondelete="cascade",
        help="Leave empty to make this reply available on all WhatsApp channels.",
    )
    team_id = fields.Many2one(
        "bird.team",
        string="Team / Queue",
        ondelete="cascade",
        help="Leave empty to make this reply available to all teams.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("bird_quick_reply_name_channel_team_uniq",
         "unique(name, channel_id, team_id)",
         "A quick reply with the same name already exists for this channel/team."),
    ]

    @api.onchange("shortcut")
    def _onchange_shortcut(self):
        for rec in self:
            if rec.shortcut:
                rec.shortcut = rec.shortcut.strip().lstrip("/")
