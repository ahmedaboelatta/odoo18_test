import base64
import binascii
import hashlib
import hmac
import io
import os
from datetime import timedelta

from PIL import Image, UnidentifiedImageError

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError, ValidationError


PBKDF2_ITERATIONS = 600_000
SENSITIVE_SECRET_FIELDS = frozenset({"secret_hash", "secret_salt"})
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class AlezdharMobileIdentity(models.Model):
    _name = "alezdhar.mobile.identity"
    _inherit = ["mail.thread", "mail.activity.mixin"]
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
    provisioning_password = fields.Char(
        string="Set mobile password",
        store=False,
        copy=False,
        groups="alezdhar_mobile_core.group_mobile_admin",
    )
    verification_policy = fields.Selection(
        [
            ("face", "Face Verification (بصمة الوجه)"),
            ("alternative", "Exempted / Alternative Verification (إعفاء - تحقق بديل)"),
        ],
        string="Attendance Verification Policy",
        required=True,
        default="face",
        tracking=True,
        help="Face Verification requires a reference selfie and live selfie check on attendance. Exempted (e.g. Niqab) uses trusted bound device + alternative verification without camera.",
    )
    exemption_reason = fields.Char(
        string="Exemption Reason / Note",
        tracking=True,
        help="Reason for face verification exemption (e.g. منتقبة - إعفاء معتمد من الموارد البشرية).",
    )
    alternative_pin = fields.Char(
        string="Alternative Verification PIN",
        copy=False,
        groups="alezdhar_mobile_core.group_mobile_admin",
        help="Optional 4-6 digit PIN for exempted employees during attendance check-in/out.",
    )
    reference_face_image = fields.Binary(
        string="Reference Face Photo",
        attachment=True,
        copy=False,
        groups="alezdhar_mobile_core.group_mobile_admin",
    )
    face_enrolled_at = fields.Datetime(
        string="Face Enrolled At",
        readonly=True,
        copy=False,
    )
    bound_device_name = fields.Char(
        string="Bound Device",
        compute="_compute_bound_device_name",
        readonly=True,
    )
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

    @staticmethod
    def _normalize_login_identifier(value):
        normalized = (value or "").strip().casefold()
        if len(normalized) < 3 or len(normalized) > 128:
            raise ValidationError(
                _("Login identifier length must be 3 to 128 characters.")
            )
        return normalized

    @api.constrains("login_identifier")
    def _check_login_identifier(self):
        for record in self:
            if record.login_identifier != self._normalize_login_identifier(
                record.login_identifier
            ):
                raise ValidationError(_("Login identifier must be normalized."))

    @api.model_create_multi
    def create(self, vals_list):
        if any(SENSITIVE_SECRET_FIELDS.intersection(vals) for vals in vals_list):
            raise AccessDenied()
        passwords = []
        for vals in vals_list:
            passwords.append(vals.pop("provisioning_password", False))
            if "login_identifier" in vals:
                vals["login_identifier"] = self._normalize_login_identifier(
                    vals["login_identifier"]
                )
        records = super().create(vals_list)
        for record, password in zip(records, passwords):
            if password:
                if not self.env.user.has_group("alezdhar_mobile_core.group_mobile_admin"):
                    raise AccessDenied()
                record._set_secret(password)
        return records

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
        if not isinstance(secret, str) or len(secret) < 6:
            raise ValidationError(_("A mobile secret must contain at least 6 characters."))
        salt = os.urandom(32)
        super(AlezdharMobileIdentity, self).write(
            {
                "secret_salt": base64.b64encode(salt).decode("ascii"),
                "secret_hash": self._derive_secret(secret, salt),
                "state": "active",
                "failed_attempts": 0,
                "locked_until": False,
            }
        )

    def write(self, vals):
        if SENSITIVE_SECRET_FIELDS.intersection(vals):
            raise AccessDenied()
        password = vals.pop("provisioning_password", False)
        if password and not self.env.user.has_group(
            "alezdhar_mobile_core.group_mobile_admin"
        ):
            raise AccessDenied()
        if "login_identifier" in vals:
            vals["login_identifier"] = self._normalize_login_identifier(
                vals["login_identifier"]
            )
        result = super().write(vals)
        if password:
            for record in self:
                record._set_secret(password)
        return result

    def _check_secret(self, secret):
        self.ensure_one()
        if not self.secret_hash or not self.secret_salt or not isinstance(secret, str):
            return False
        calculated = self._derive_secret(secret, base64.b64decode(self.secret_salt))
        return hmac.compare_digest(calculated, self.secret_hash)

    @api.model
    def authenticate_password(self, login_identifier, password):
        if not isinstance(password, str):
            raise AccessDenied()
        try:
            normalized = self._normalize_login_identifier(login_identifier)
        except ValidationError:
            raise AccessDenied()
        identity = self.sudo().search(
            [("login_identifier", "=", normalized)], limit=1
        )
        now = fields.Datetime.now()
        if not identity:
            raise AccessDenied()
        if identity.locked_until and identity.locked_until > now:
            raise AccessDenied()
        if not identity._check_secret(password):
            attempts = identity.failed_attempts + 1
            values = {"failed_attempts": attempts}
            if attempts >= MAX_FAILED_ATTEMPTS:
                values.update(
                    {
                        "state": "locked",
                        "locked_until": now + timedelta(minutes=LOCKOUT_MINUTES),
                    }
                )
            super(AlezdharMobileIdentity, identity).write(values)
            raise AccessDenied()
        if identity.state == "locked" and identity.locked_until and identity.locked_until <= now:
            super(AlezdharMobileIdentity, identity).write({"state": "active"})
        identity._assert_can_authenticate()
        super(AlezdharMobileIdentity, identity).write(
            {
                "failed_attempts": 0,
                "locked_until": False,
                "last_authenticated_at": now,
            }
        )
        return identity

    def _assert_can_authenticate(self):
        self.ensure_one()
        if not self.active or self.state != "active":
            raise AccessDenied()
        if not self.employee_id.active or not self.employee_id.company_id.active:
            raise AccessDenied()

    def _compute_bound_device_name(self):
        for record in self:
            active_device = record.device_ids.filtered(
                lambda d: d.trusted and not d.revoked_at
            )[:1]
            record.bound_device_name = (
                f"{active_device.name} ({active_device.platform})"
                if active_device
                else False
            )

    def action_reset_bound_devices(self):
        for record in self:
            active_devices = record.device_ids.filtered(lambda d: not d.revoked_at)
            if active_devices:
                active_devices.action_revoke()
            record.message_post(
                body=_(
                    "Bound mobile device(s) have been reset by %s. The employee can now sign in from a new phone."
                )
                % self.env.user.name
            )

    def action_clear_face_enrollment(self):
        for record in self:
            super(AlezdharMobileIdentity, record).write(
                {"reference_face_image": False, "face_enrolled_at": False}
            )
            record.message_post(
                body=_("Reference face photo has been reset by %s.")
                % self.env.user.name
            )

    def enroll_reference_face(self, image_base64):
        self.ensure_one()
        self._assert_can_authenticate()
        raw_str = str(image_base64 or "").strip()
        if "," in raw_str and raw_str.startswith("data:"):
            raw_str = raw_str.split(",", 1)[1]
        try:
            raw_bytes = base64.b64decode(raw_str, validate=True)
            if not raw_bytes or len(raw_bytes) > 5 * 1024 * 1024:
                raise ValidationError(_("Reference photo must be under 5 MB."))
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img.verify()
            with Image.open(io.BytesIO(raw_bytes)) as img:
                rgb = img.convert("RGB")
                if rgb.width < 64 or rgb.height < 64:
                    raise ValidationError(_("Reference photo resolution is too small."))
                rgb.thumbnail((640, 640))
                out = io.BytesIO()
                rgb.save(out, format="JPEG", quality=85)
                normalized_b64 = base64.b64encode(out.getvalue()).decode("ascii")
        except (binascii.Error, UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValidationError(_("A valid clear face photo is required.")) from exc
        now = fields.Datetime.now()
        super(AlezdharMobileIdentity, self).write(
            {
                "reference_face_image": normalized_b64,
                "face_enrolled_at": now,
            }
        )
        if not self.employee_id.sudo().image_1920:
            self.employee_id.sudo().write({"image_1920": normalized_b64})

    def safe_profile_dto(self):
        self.ensure_one()
        self._assert_can_authenticate()
        employee = self.employee_id.sudo()
        avatar = employee.image_128
        if isinstance(avatar, bytes):
            avatar = avatar.decode("ascii")
        active_device = self.device_ids.filtered(
            lambda d: d.trusted and not d.revoked_at
        )[:1]
        is_manager = bool(
            self.env["hr.employee"]
            .sudo()
            .search_count(
                [("parent_id", "=", employee.id), ("id", "!=", employee.id)]
            )
        )
        return {
            "employee_ref": employee.id,
            "name": employee.name,
            "job_title": employee.job_title
            or (employee.job_id.name if employee.job_id else ""),
            "company": employee.company_id.name,
            "avatar_base64": avatar or None,
            "employee_number": self.login_identifier,
            "department": employee.department_id.name or "",
            "manager": employee.parent_id.name or "",
            "work_email": employee.work_email or "",
            "work_phone": employee.mobile_phone or employee.work_phone or "",
            "verification_policy": self.verification_policy or "face",
            "face_enrolled": bool(self.reference_face_image),
            "exemption_reason": self.exemption_reason or "",
            "requires_alternative_pin": bool(self.alternative_pin),
            "bound_device_name": active_device.name if active_device else "",
            "is_manager": is_manager,
        }
