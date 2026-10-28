from odoo import api, fields, models


class AlezdharMobileFeature(models.Model):
    _name = "alezdhar.mobile.feature"
    _description = "Alezdhar Mobile Feature"
    _order = "sequence, key"

    name = fields.Char(required=True, translate=True)
    key = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    enabled = fields.Boolean(default=False)
    minimum_app_version = fields.Char(default="0.1.0")
    requires_authentication = fields.Boolean(default=True)

    _sql_constraints = [
        ("key_unique", "UNIQUE(key)", "Feature key must be unique.")
    ]

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

    alezdhar_mobile_auth_provider = fields.Selection(
        [("disabled", "Disabled")],
        string="Mobile authentication provider",
        default="disabled",
        config_parameter="alezdhar_mobile.auth_provider",
    )
    alezdhar_mobile_api_enabled = fields.Boolean(
        string="Enable authenticated mobile API",
        default=False,
        config_parameter="alezdhar_mobile.api_enabled",
    )

