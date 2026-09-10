from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_whatsapp_bridge_enabled = fields.Boolean(
        string="Enable AI WhatsApp Bridge",
        config_parameter="ai_whatsapp_bridge.enabled",
        default=True,
    )
