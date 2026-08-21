from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BirdTeam(models.Model):
    _name = 'bird.team'
    _description = 'Bird Conversation Team'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color')
    manager_id = fields.Many2one('res.users', string='Team Leader', domain=[('share', '=', False)])
    member_ids = fields.Many2many(
        'res.users', 'bird_team_user_rel', 'team_id', 'user_id', string='Members',
        domain=[('share', '=', False)],
        help='Internal users who can be assigned conversations in this queue.'
    )
    conversation_ids = fields.One2many('bird.conversation', 'team_id', string='Conversations')
    conversation_count = fields.Integer(compute='_compute_conversation_count')

    @api.depends('conversation_ids')
    def _compute_conversation_count(self):
        for rec in self:
            rec.conversation_count = len(rec.conversation_ids)

    @api.constrains('manager_id', 'member_ids')
    def _check_manager_member(self):
        for rec in self:
            if rec.manager_id and rec.manager_id.share:
                raise ValidationError(_('Team Leader must be an internal Odoo user.'))
