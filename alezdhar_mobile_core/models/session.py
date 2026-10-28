import hashlib
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, ValidationError


class AlezdharMobileSession(models.Model):
    _name = "alezdhar.mobile.session"
    _description = "Alezdhar Mobile Session"
    _order = "create_date desc"
    _rec_name = "device_id"

    identity_id = fields.Many2one(
        "alezdhar.mobile.identity", required=True, index=True, ondelete="cascade"
    )
    device_id = fields.Many2one(
        "alezdhar.mobile.device", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(related="identity_id.company_id", store=True, index=True)
    access_token_hash = fields.Char(required=True, index=True, copy=False)
    access_expires_at = fields.Datetime(required=True, index=True)
    refresh_token_hash = fields.Char(required=True, index=True, copy=False)
    refresh_expires_at = fields.Datetime(required=True, index=True)
    revoked_at = fields.Datetime(readonly=True, index=True)
    last_seen_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "access_token_unique",
            "UNIQUE(access_token_hash)",
            "Access token hash must be unique.",
        ),
        (
            "refresh_token_unique",
            "UNIQUE(refresh_token_hash)",
            "Refresh token hash must be unique.",
        ),
    ]

    @api.constrains("identity_id", "device_id")
    def _check_device_identity(self):
        for session in self:
            if session.device_id.identity_id != session.identity_id:
                raise ValidationError(
                    _("A mobile session device must belong to the same identity.")
                )

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @api.model
    def issue(self, identity, device, access_expires_at, refresh_expires_at):
        identity._assert_can_authenticate()
        if device.identity_id != identity or device.revoked_at:
            raise AccessDenied()
        access_token = secrets.token_urlsafe(48)
        refresh_token = secrets.token_urlsafe(64)
        session = self.sudo().create(
            {
                "identity_id": identity.id,
                "device_id": device.id,
                "access_token_hash": self.hash_token(access_token),
                "access_expires_at": access_expires_at,
                "refresh_token_hash": self.hash_token(refresh_token),
                "refresh_expires_at": refresh_expires_at,
            }
        )
        return session, access_token, refresh_token

    @api.model
    def authenticate_access_token(self, token):
        if not isinstance(token, str) or len(token) < 32:
            raise AccessDenied()
        session = self.sudo().search(
            [("access_token_hash", "=", self.hash_token(token))], limit=1
        )
        now = fields.Datetime.now()
        if (
            not session
            or session.revoked_at
            or session.access_expires_at <= now
            or session.device_id.revoked_at
        ):
            raise AccessDenied()
        session.identity_id._assert_can_authenticate()
        session.sudo().write({"last_seen_at": now})
        return session

