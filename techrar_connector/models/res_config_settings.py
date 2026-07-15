from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    techrar_api_base_url = fields.Char(
        string='Techrar API Base URL',
        config_parameter='techrar.api_base_url',
        default='https://api.techrar.com',
    )
    techrar_api_token = fields.Char(
        string='Techrar API Token',
        config_parameter='techrar.api_token',
        password=True,
    )
    techrar_app_id = fields.Char(
        string='Techrar App ID',
        config_parameter='techrar.app_id',
        default='3',
    )
