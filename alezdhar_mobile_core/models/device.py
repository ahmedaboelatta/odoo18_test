from odoo import fields, models


class AlezdharMobileDevice(models.Model):
    _name = "alezdhar.mobile.device"
    _description = "Alezdhar Mobile Device"
    _order = "last_seen_at desc, id desc"

    identity_id = fields.Many2one(
        "alezdhar.mobile.identity", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(related="identity_id.company_id", store=True, index=True)
    name = fields.Char(required=True)
    installation_id = fields.Char(required=True, index=True, copy=False)
    platform = fields.Selection(
        [("android", "Android"), ("ios", "iOS")], required=True
    )
    trusted = fields.Boolean(default=False, readonly=True)
    revoked_at = fields.Datetime(readonly=True)
    last_seen_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "installation_unique",
            "UNIQUE(installation_id)",
            "Device installation identifier must be unique.",
        )
    ]

    def action_revoke(self):
        now = fields.Datetime.now()
        self.write({"revoked_at": now, "trusted": False})
        self.mapped("identity_id.session_ids").filtered(
            lambda session: session.device_id in self and not session.revoked_at
        ).write({"revoked_at": now})

