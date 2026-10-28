import base64
import hashlib
import hmac
import os

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError, ValidationError


PBKDF2_ITERATIONS = 600_000


class AlezdharMobileIdentity(models.Model):
    _name = "alezdhar.mobile.identity"
    _description = "Alezdhar Mobile Identity"
    _order = "employee_id"
    _rec_name = "employee_id"

    employee_id = fields.Many2one(
        "hr.employee", required=True, index=True, ondelete="restrict"
    )
    company_id = fields.Many2one(
        related="employee_id.company_id", store=True, index=True, readonly=True
    )
    login_identifier = fields.Char(required=True, index=True, copy=False)
    state = fields.Selection(
        [
            ("invited", "Invited"),
            ("active", "Active"),
            ("locked", "Locked"),
            ("revoked", "Revoked"),
        ],
        required=True,
        default="invited",
        index=True,
    )
    active = fields.Boolean(default=True)
    secret_hash = fields.Char(copy=False, groups="alezdhar_mobile_core.group_mobile_admin")
    secret_salt = fields.Char(copy=False, groups="alezdhar_mobile_core.group_mobile_admin")
    failed_attempts = fields.Integer(default=0, readonly=True)
    locked_until = fields.Datetime(readonly=True)
    last_authenticated_at = fields.Datetime(readonly=True)
    device_ids = fields.One2many("alezdhar.mobile.device", "identity_id")
    session_ids = fields.One2many("alezdhar.mobile.session", "identity_id")

    _sql_constraints = [
        (
            "employee_unique",
            "UNIQUE(employee_id)",
            "An employee can have only one mobile identity.",
        ),
        (
            "login_unique",
            "UNIQUE(login_identifier)",
            "The mobile login identifier must be unique.",
        ),
    ]

    @api.constrains("login_identifier")
    def _check_login_identifier(self):
        for record in self:
            normalized = (record.login_identifier or "").strip().casefold()
            if len(normalized) < 3 or len(normalized) > 128:
                raise ValidationError(_("Login identifier length must be 3 to 128 characters."))
            record.login_identifier = normalized

    @staticmethod
    def _derive_secret(secret, salt):
        return base64.b64encode(
            hashlib.pbkdf2_hmac(
                "sha256", secret.encode("utf-8"), salt, PBKDF2_ITERATIONS
            )
        ).decode("ascii")

    def action_set_initial_secret(self):
        raise UserError(
            _(
                "No credential provider is enabled. Configure a vetted activation/OTP "
                "provider before issuing mobile credentials."
            )
        )

    def _set_secret(self, secret):
        """Internal/test helper. Provider adapters must validate enrollment first."""
        self.ensure_one()
        if not isinstance(secret, str) or len(secret) < 12:
            raise ValidationError(_("A mobile secret must contain at least 12 characters."))
        salt = os.urandom(32)
        self.write(
            {
                "secret_salt": base64.b64encode(salt).decode("ascii"),
                "secret_hash": self._derive_secret(secret, salt),
                "state": "active",
                "failed_attempts": 0,
                "locked_until": False,
            }
        )

    def _check_secret(self, secret):
        self.ensure_one()
        if not self.secret_hash or not self.secret_salt or not isinstance(secret, str):
            return False
        calculated = self._derive_secret(secret, base64.b64decode(self.secret_salt))
        return hmac.compare_digest(calculated, self.secret_hash)

    def _assert_can_authenticate(self):
        self.ensure_one()
        if not self.active or self.state != "active":
            raise AccessDenied()
        if not self.employee_id.active or not self.employee_id.company_id.active:
            raise AccessDenied()

    def safe_profile_dto(self):
        self.ensure_one()
        self._assert_can_authenticate()
        employee = self.employee_id
        return {
            "employee_ref": employee.id,
            "name": employee.name,
            "job_title": employee.job_title or "",
            "company": employee.company_id.name,
        }

