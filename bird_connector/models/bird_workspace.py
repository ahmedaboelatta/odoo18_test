from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BirdWorkspace(models.Model):
    _name = 'bird.workspace'
    _description = 'Bird Workspace'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, track_visibility='onchange')
    organization_id = fields.Many2one('bird.organization', string='Organization', required=True, ondelete='cascade')
    workspace_id = fields.Char(string='Bird Workspace ID')
    channel_ids = fields.One2many('bird.channel', 'workspace_id', string='Channels')
    template_ids = fields.One2many('bird.template', 'workspace_id', string='Templates')
    conversation_ids = fields.One2many('bird.conversation', 'workspace_id', string='Conversations')
