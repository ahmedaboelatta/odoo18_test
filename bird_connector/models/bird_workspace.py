from odoo import models, fields, api


class BirdWorkspace(models.Model):
    _name = "bird.workspace"
    _description = "Bird Workspace"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Workspace Name", required=True, tracking=True)
    workspace_id = fields.Char(string="Workspace ID", required=True, tracking=True)
    organization_id = fields.Many2one(
        "bird.organization", string="Organization", required=True, ondelete="cascade"
    )
    channel_ids = fields.One2many("bird.channel", "workspace_id", string="Channels")
    template_ids = fields.One2many("bird.template", "workspace_id", string="Templates")
    state = fields.Selection(
        [("active", "Active"), ("inactive", "Inactive")],
        string="State",
        default="active",
        tracking=True,
    )

    def action_sync_templates(self):
        self.ensure_one()
        return self.env["bird.template"].action_sync_templates(self.id)
