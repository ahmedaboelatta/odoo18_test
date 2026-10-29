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
    push_installation_id = fields.Char(
        string="Firebase Installation ID", index=True, copy=False, readonly=True
    )
    push_registered_at = fields.Datetime(readonly=True)
    push_enabled = fields.Boolean(default=False, readonly=True)
    push_locale = fields.Selection(
        [("ar", "Arabic"), ("en", "English")], default="ar", readonly=True
    )

    _sql_constraints = [
        (
            "installation_unique",
            "UNIQUE(installation_id)",
            "Device installation identifier must be unique.",
        ),
        (
            "push_installation_unique",
            "UNIQUE(push_installation_id)",
            "Firebase Installation ID must be unique.",
        ),
    ]

    def action_revoke(self):
        now = fields.Datetime.now()
        self.write({"revoked_at": now, "trusted": False, "push_enabled": False})
        self.mapped("identity_id.session_ids").filtered(
            lambda session: session.device_id in self and not session.revoked_at
        ).sudo().write({"revoked_at": now})

