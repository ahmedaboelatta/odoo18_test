from odoo import api, fields, models


class BirdQuickReply(models.Model):
    _name = 'bird.quick.reply'
    _description = 'Bird Quick Reply'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, index=True)
    shortcut = fields.Char(help='Optional shortcut, e.g. welcome. Users can find it by typing /welcome.')
    message = fields.Text(required=True)
    team_id = fields.Many2one('bird.team', string='Team / Queue', ondelete='set null')
    channel_id = fields.Many2one('bird.channel', string='WhatsApp Channel', ondelete='set null')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.model
    def inbox_get_quick_replies(self, team_id=False, channel_id=False, search_term=False):
        domain = [('active', '=', True)]
        # Global replies plus replies scoped to the active team/channel.
        if team_id:
            domain += ['|', ('team_id', '=', False), ('team_id', '=', int(team_id))]
        else:
            domain.append(('team_id', '=', False))
        if channel_id:
            domain += ['|', ('channel_id', '=', False), ('channel_id', '=', int(channel_id))]
        else:
            domain.append(('channel_id', '=', False))
        term = (search_term or '').strip().lstrip('/')
        if term:
            domain += ['|', '|', ('name', 'ilike', term), ('shortcut', 'ilike', term), ('message', 'ilike', term)]
        rows = self.sudo().search(domain, limit=50)
        return [{'id': r.id, 'name': r.name, 'shortcut': r.shortcut or '', 'message': r.message or ''} for r in rows]
