from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BirdRoutingRule(models.Model):
    _name = "bird.routing.rule"
    _description = "Bird Auto-Routing Rule"
    _order = "sequence, id"

    name = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10, help="Lower numbers are evaluated first.")
    active = fields.Boolean(default=True)
    channel_id = fields.Many2one("bird.channel", string="WhatsApp Channel", ondelete="cascade", index=True,
        domain="[('channel_type','=','whatsapp')]", help="Leave empty to match any channel.")
    tag_id = fields.Many2one("bird.contact.tag", string="Contact Tag", ondelete="cascade", index=True,
        help="Leave empty to match any contact tag.")
    keyword = fields.Char(string="Message Contains", help="Case-insensitive text match. Leave empty to match any message.")
    team_id = fields.Many2one("bird.team", string="Route To Team / Queue", required=True, ondelete="cascade", index=True)
    assigned_user_id = fields.Many2one("res.users", string="Default Assignee", ondelete="set null",
        domain="[('share','=',False)]", help="Optional. Must be a member or leader of the selected team.")
    conversation_count = fields.Integer(string="Routed Conversations", readonly=True, default=0)

    @api.constrains('team_id', 'assigned_user_id')
    def _check_assignee_team(self):
        for rec in self:
            if rec.assigned_user_id and rec.team_id:
                allowed = rec.team_id.member_ids | rec.team_id.manager_id
                if rec.assigned_user_id not in allowed:
                    raise ValidationError(_("Default Assignee must be a member or leader of the selected team."))

    def matches(self, conversation, message_text=''):
        self.ensure_one()
        if self.channel_id and self.channel_id != conversation.channel_id:
            return False
        if self.tag_id and self.tag_id not in conversation.contact_id.tag_ids:
            return False
        if self.keyword and self.keyword.lower() not in (message_text or '').lower():
            return False
        return True
