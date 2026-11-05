from odoo import api, fields, models


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def get_param(self, key, default=False):
        return self.get_str(key, default)

    @api.model
    def set_param(self, key, value):
        return self.set_str(key, value)


class HaderMobileFeature(models.Model):
    _name = "hader.mobile.feature"
    _description = "Hader Mobile Feature"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, key"

    name = fields.Char(required=True, translate=True)
    key = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    enabled = fields.Boolean(default=False, tracking=True)
    minimum_app_version = fields.Char(default="0.1.0")
    requires_authentication = fields.Boolean(default=True)

    _sql_constraints = [("key_unique", "UNIQUE(key)", "Feature key must be unique.")]

    @api.model
    def bootstrap_dto(self):
        return [
            {
                "key": feature.key,
                "enabled": feature.enabled,
                "minimum_app_version": feature.minimum_app_version,
            }
            for feature in self.sudo().search([("active", "=", True)])
        ]


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hader_mobile_auth_provider = fields.Selection(
        [("disabled", "Disabled"), ("password", "Employee number and password")],
        string="Mobile authentication provider",
        default="disabled",
        config_parameter="hader_mobile.auth_provider",
    )
    hader_mobile_api_enabled = fields.Boolean(
        string="Enable authenticated mobile API",
        default=False,
        config_parameter="hader_mobile.api_enabled",
    )
