from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    bird_access_key = fields.Char(
        string="Bird Access Key",
        config_parameter="bird.access_key",
    )
    bird_workspace_id = fields.Char(
        string="Bird Workspace ID",
        config_parameter="bird.workspace_id",
    )
