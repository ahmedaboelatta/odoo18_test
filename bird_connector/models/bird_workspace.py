from odoo import models, fields, api
from odoo.exceptions import UserError

class BirdWorkspace(models.Model):
    _name = 'bird.workspace'
    _description = 'Bird Workspace'

    name = fields.Char(string='Workspace Name', required=True)
    workspace_id = fields.Char(string='Workspace ID', required=True)
    organization_id = fields.Many2one('bird.organization', string='Organization', ondelete='cascade')
    
    state = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ], string='Status', default='active')

    channel_ids = fields.One2many('bird.channel', 'workspace_id', string='Channels')
    template_ids = fields.One2many('bird.template', 'workspace_id', string='Templates')

    def action_sync_templates(self):
        self.ensure_one()
        if not self.organization_id:
            raise UserError("This workspace is not linked to any organization setup.")
        return self.organization_id.action_sync_workspaces_and_channels(target_workspace_id=self.workspace_id)
