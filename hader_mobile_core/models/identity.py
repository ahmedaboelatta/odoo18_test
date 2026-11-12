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


class HaderMobileIdentity(models.Model):
    _name = "hader.mobile.identity"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Hader Mobile Identity"
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
    secret_hash = fields.Char(copy=False, groups="hader_mobile_core.group_mobile_admin")
    secret_salt = fields.Char(copy=False, groups="hader_mobile_core.group_mobile_admin")
    failed_attempts = fields.Integer(default=0, readonly=True)
    locked_until = fields.Datetime(readonly=True)
    last_authenticated_at = fields.Datetime(readonly=True)
    provisioning_password = fields.Char(
        string="Set mobile password",
        store=False,
        copy=False,
        groups="hader_mobile_core.group_mobile_admin",
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
        groups="hader_mobile_core.group_mobile_admin",
        help="Optional 4-6 digit PIN for exempted employees during attendance check-in/out.",
    )
    reference_face_image = fields.Binary(
        string="Reference Face Photo",
        attachment=True,
        copy=False,
        groups="hader_mobile_core.group_mobile_admin",
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
    device_ids = fields.One2many("hader.mobile.device", "identity_id")
    session_ids = fields.One2many("hader.mobile.session", "identity_id")

    if hasattr(models, "Constraint"):
        _employee_unique = models.Constraint(
            "UNIQUE(employee_id)",
            "An employee can have only one mobile identity.",
        )
        _login_unique = models.Constraint(
            "UNIQUE(login_identifier)",
            "The mobile login identifier must be unique.",
        )
    else:
        _sql_constraints = [
            ("employee_unique", "UNIQUE(employee_id)", "An employee can have only one mobile identity."),
            ("login_unique", "UNIQUE(login_identifier)", "The mobile login identifier must be unique."),
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
        for record in records:
            self.env["hader.mobile.subscription"].verify_company_subscription(
                record.company_id, check_new_seat=True
            )
        for record, password in zip(records, passwords):
            if password:
                if not self.env.user.has_group("hader_mobile_core.group_mobile_admin"):
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
        super(HaderMobileIdentity, self).write(
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
            "hader_mobile_core.group_mobile_admin"
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
            super(HaderMobileIdentity, identity).write(values)
            raise AccessDenied()
        if identity.state == "locked" and identity.locked_until and identity.locked_until <= now:
            super(HaderMobileIdentity, identity).write({"state": "active"})
        identity._assert_can_authenticate()
        super(HaderMobileIdentity, identity).write(
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
        try:
            self.env["hader.mobile.subscription"].verify_company_subscription(
                self.company_id, check_new_seat=False
            )
        except ValidationError as exc:
            raise AccessDenied(str(exc)) from exc

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
            super(HaderMobileIdentity, record).write(
                {"reference_face_image": False, "face_enrolled_at": False}
            )
            record.message_post(
                body=_("Reference face photo has been reset by %s.")
                % self.env.user.name
            )

    def enroll_reference_face(self, image_base64):
        self.ensure_one()
        self._assert_can_authenticate()
        if self.reference_face_image:
            raise ValidationError(
                _("تم تسجيل الصورة المرجعية للوجه مسبقاً ولا يمكن تعديلها إلا عن طريق الموارد البشرية. / Reference face photo is already enrolled and cannot be modified.")
            )
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
                normalized_bytes = out.getvalue()
                normalized_b64 = base64.b64encode(normalized_bytes).decode("ascii")
        except (binascii.Error, UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValidationError(_("A valid clear face photo is required.")) from exc
        self._validate_enrolled_face_biometrics(normalized_bytes)
        now = fields.Datetime.now()
        super(HaderMobileIdentity, self).write(
            {
                "reference_face_image": normalized_b64,
                "face_enrolled_at": now,
            }
        )
        self.employee_id.sudo().write({"image_1920": normalized_b64})

    def _validate_enrolled_face_biometrics(self, image_bytes):
        yunet_path = "/var/lib/odoo/face_models/face_detection_yunet_2023mar.onnx"
        sface_path = "/var/lib/odoo/face_models/face_recognition_sface_2021dec.onnx"
        if not (os.path.exists(yunet_path) and os.path.exists(sface_path)):
            return
        try:
            import cv2
            import numpy as np
        except ImportError:
            return
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValidationError(_("الصورة الملتقطة غير صالحة. يرجى إعادة المحاولة."))
        h, w = img.shape[:2]
        detector = cv2.FaceDetectorYN.create(yunet_path, "", (w, h), 0.75, 0.3, 5000)
        _ok, faces = detector.detect(img)
        if faces is None or len(faces) == 0:
            raise ValidationError(
                _("لم يتم اكتشاف وجه واضح في الصورة. يرجى وضع الوجه داخل الإطار البيضاوي في إضاءة جيدة.")
            )
        if len(faces) > 1:
            raise ValidationError(
                _("تم اكتشاف أكثر من وجه في الصورة. يرجى التقاط الصورة بمفردك.")
            )
        face = faces[0]
        recognizer = cv2.FaceRecognizerSF.create(sface_path, "")
        aligned = recognizer.alignCrop(img, face)
        new_feat = recognizer.feature(aligned)

        # If HR already uploaded an employee profile photo with a clear human face, verify it matches
        emp_img_b64 = self.employee_id.sudo().image_1920
        if emp_img_b64:
            try:
                emp_bytes = emp_img_b64.content if hasattr(emp_img_b64, "content") else base64.b64decode(emp_img_b64)
                emp_arr = np.frombuffer(emp_bytes, dtype=np.uint8)
                emp_img = cv2.imdecode(emp_arr, cv2.IMREAD_COLOR)
                if emp_img is not None:
                    eh, ew = emp_img.shape[:2]
                    emp_det = cv2.FaceDetectorYN.create(yunet_path, "", (ew, eh), 0.75, 0.3, 5000)
                    _eok, emp_faces = emp_det.detect(emp_img)
                    if emp_faces is not None and len(emp_faces) == 1:
                        emp_aligned = recognizer.alignCrop(emp_img, emp_faces[0])
                        emp_feat = recognizer.feature(emp_aligned)
                        cos_hr = recognizer.match(new_feat, emp_feat, cv2.FaceRecognizerSF_FR_COSINE)
                        if cos_hr < 0.38:
                            raise ValidationError(
                                _("الصورة الملتقطة لا تتطابق مع صورة الموظف المسجلة في ملف الموارد البشرية.")
                            )
            except ValidationError:
                raise
            except Exception:
                pass

        # Prevent enrolling the same person's face on another employee's identity
        other_identities = self.sudo().search([
            ("id", "!=", self.id),
            ("reference_face_image", "!=", False),
        ])
        for other in other_identities:
            try:
                other_ref = other.reference_face_image
                other_bytes = other_ref.content if hasattr(other_ref, "content") else base64.b64decode(other_ref)
                other_arr = np.frombuffer(other_bytes, dtype=np.uint8)
                other_img = cv2.imdecode(other_arr, cv2.IMREAD_COLOR)
                if other_img is None:
                    continue
                oh, ow = other_img.shape[:2]
                other_det = cv2.FaceDetectorYN.create(yunet_path, "", (ow, oh), 0.75, 0.3, 5000)
                _ook, other_faces = other_det.detect(other_img)
                if other_faces is not None and len(other_faces) > 0:
                    other_aligned = recognizer.alignCrop(other_img, other_faces[0])
                    other_feat = recognizer.feature(other_aligned)
                    cos_other = recognizer.match(new_feat, other_feat, cv2.FaceRecognizerSF_FR_COSINE)
                    if cos_other >= 0.45:
                        raise ValidationError(
                            _("بصمة الوجه هذه مسجلة لموظف آخر بالفعل ولا يمكن استخدامها لأكثر من موظف.")
                        )
            except ValidationError:
                raise
            except Exception:
                continue

    def safe_profile_dto(self):
        self.ensure_one()
        self._assert_can_authenticate()
        employee = self.employee_id.sudo()
        avatar = employee.image_128
        if hasattr(avatar, "content"):
            avatar = base64.b64encode(avatar.content).decode("ascii") if avatar.content else None
        elif isinstance(avatar, bytes):
            avatar = avatar.decode("ascii")
        active_device = self.device_ids.filtered(
            lambda d: d.trusted and not d.revoked_at
        )[:1]
        is_manager = employee._is_any_mobile_manager()
        has_user = bool(employee.user_id)
        sub = self.env["hader.mobile.subscription"].sudo().search(
            [("company_id", "=", employee.company_id.id)], order="id desc", limit=1
        ) or self.env["hader.mobile.subscription"].sudo().search([], order="id desc", limit=1)
        calendar_feature_on = bool(sub.feature_calendar) if sub else True
        has_calendar = bool("calendar.event" in self.env and calendar_feature_on)
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
            "coach": employee.coach_id.name if "coach_id" in employee._fields and employee.coach_id else "",
            "work_email": employee.work_email or "",
            "work_phone": employee.mobile_phone or employee.work_phone or "",
            "office_phone": employee.work_phone or "",
            "mobile_phone": employee.mobile_phone or "",
            "work_location": (
                employee.work_location_id.name
                if "work_location_id" in employee._fields and employee.work_location_id
                else ""
            ),
            "working_schedule": (
                employee.resource_calendar_id.name
                if employee.resource_calendar_id
                else ""
            ),
            "first_contract_date": (
                employee.first_contract_date.isoformat()
                if "first_contract_date" in employee._fields and employee.first_contract_date
                else ""
            ),
            "nationality": (
                employee.country_id.name
                if "country_id" in employee._fields and employee.country_id
                else ""
            ),
            "country_of_birth": (
                employee.country_of_birth.name
                if "country_of_birth" in employee._fields and employee.country_of_birth
                else ""
            ),
            "place_of_birth": (
                str(employee.place_of_birth or "")
                if "place_of_birth" in employee._fields
                else ""
            ),
            "birthday": (
                employee.birthday.isoformat()
                if "birthday" in employee._fields and employee.birthday
                else ""
            ),
            "gender": (
                str(employee.gender or "")
                if "gender" in employee._fields
                else ""
            ),
            "marital": (
                str(employee.marital or "")
                if "marital" in employee._fields
                else ""
            ),
            "certificate": (
                str(employee.certificate or "")
                if "certificate" in employee._fields
                else ""
            ),
            "study_field": (
                str(employee.study_field or "")
                if "study_field" in employee._fields
                else ""
            ),
            "study_school": (
                str(employee.study_school or "")
                if "study_school" in employee._fields
                else ""
            ),
            "private_phone": (
                str(employee.private_phone or "")
                if "private_phone" in employee._fields
                else ""
            ),
            "private_email": (
                str(employee.private_email or "")
                if "private_email" in employee._fields
                else ""
            ),
            "emergency_contact": (
                str(employee.emergency_contact or "")
                if "emergency_contact" in employee._fields
                else ""
            ),
            "emergency_phone": (
                str(employee.emergency_phone or "")
                if "emergency_phone" in employee._fields
                else ""
            ),
            "identification_id": (
                str(employee.identification_id or "")
                if "identification_id" in employee._fields
                else ""
            ),
            "passport_id": (
                str(employee.passport_id or "")
                if "passport_id" in employee._fields
                else ""
            ),
            "visa_expire": (
                employee.visa_expire.isoformat()
                if "visa_expire" in employee._fields and employee.visa_expire
                else ""
            ),
            "work_permit_expiration_date": (
                employee.work_permit_expiration_date.isoformat()
                if "work_permit_expiration_date" in employee._fields and employee.work_permit_expiration_date
                else ""
            ),
            "verification_policy": self.verification_policy or "face",
            "face_enrolled": bool(self.reference_face_image),
            "exemption_reason": self.exemption_reason or "",
            "requires_alternative_pin": bool(self.alternative_pin),
            "bound_device_name": active_device.name if active_device else "",
            "is_manager": is_manager,
            "has_user": has_user,
            "has_calendar": has_calendar,
        }

    def contract_dto(self):
        """Return the authenticated employee's own employment contract and salary breakdown."""
        self.ensure_one()
        self._assert_can_authenticate()
        employee = self.employee_id.sudo()
        company = employee.company_id
        currency = (
            company.currency_id.symbol
            or company.currency_id.name
            or "SAR"
        )
        first_date = (
            employee.first_contract_date.isoformat()
            if "first_contract_date" in employee._fields and employee.first_contract_date
            else ""
        )
        if "hr.contract" in self.env:
            Contract = self.env["hr.contract"].sudo()
            contract = Contract.search(
                [("employee_id", "=", employee.id), ("state", "=", "open")],
                order="date_start desc, id desc",
                limit=1,
            ) or Contract.search(
                [("employee_id", "=", employee.id)],
                order="date_start desc, id desc",
                limit=1,
            )
            if contract:
                basic_wage = float(contract.wage or 0.0)
                allowances = []
                if "allowance_ids" in contract._fields and contract.allowance_ids:
                    for line in contract.allowance_ids:
                        amt = float(getattr(line, "total_amount", 0.0) or getattr(line, "amount", 0.0) or 0.0)
                        if amt > 0:
                            allowances.append({
                                "name": getattr(line.allowance_id, "name", "") or getattr(line, "name", "بدل إضافي"),
                                "code": getattr(line, "code", "") or "",
                                "amount": round(amt, 2),
                            })
                for fname, label_ar, label_en in (
                    ("housing_allowance", "بدل سكن", "Housing Allowance"),
                    ("hra", "بدل سكن", "Housing Allowance"),
                    ("transportation_allowance", "بدل انتقال", "Transportation Allowance"),
                    ("travel_allowance", "بدل انتقال", "Transportation Allowance"),
                    ("meal_allowance", "بدل إعاشة", "Meal Allowance"),
                    ("medical_allowance", "بدل طبي", "Medical Allowance"),
                    ("other_allowance", "بدلات أخرى", "Other Allowance"),
                    ("da", "بدل غلاء معيشة", "Dearness Allowance"),
                ):
                    if fname in contract._fields:
                        val = float(contract[fname] or 0.0)
                        if val > 0:
                            allowances.append({
                                "name": label_ar,
                                "name_en": label_en,
                                "code": fname.upper(),
                                "amount": round(val, 2),
                            })
                total_allowances = round(sum(item["amount"] for item in allowances), 2)
                total_salary = round(basic_wage + total_allowances, 2)
                struct_name = ""
                if "struct_id" in contract._fields and contract.struct_id:
                    struct_name = contract.struct_id.name or ""
                elif "structure_type_id" in contract._fields and contract.structure_type_id:
                    struct_name = contract.structure_type_id.name or ""
                return {
                    "has_contract": True,
                    "id": contract.id,
                    "name": contract.name or "",
                    "state": contract.state or "open",
                    "employee_name": employee.name or "",
                    "employee_number": self.login_identifier or "",
                    "job_title": (
                        (contract.job_id.name if contract.job_id else "")
                        or employee.job_title
                        or (employee.job_id.name if employee.job_id else "")
                    ),
                    "department": (
                        (contract.department_id.name if contract.department_id else "")
                        or (employee.department_id.name if employee.department_id else "")
                    ),
                    "contract_type": (
                        contract.contract_type_id.name
                        if "contract_type_id" in contract._fields and contract.contract_type_id
                        else ""
                    ),
                    "structure_name": struct_name,
                    "working_schedule": (
                        (contract.resource_calendar_id.name if contract.resource_calendar_id else "")
                        or (employee.resource_calendar_id.name if employee.resource_calendar_id else "")
                    ),
                    "schedule_pay": (
                        str(contract.schedule_pay or "monthly")
                        if "schedule_pay" in contract._fields
                        else "monthly"
                    ),
                    "date_start": contract.date_start.isoformat() if contract.date_start else first_date,
                    "date_end": contract.date_end.isoformat() if contract.date_end else "",
                    "trial_date_end": (
                        contract.trial_date_end.isoformat()
                        if "trial_date_end" in contract._fields and contract.trial_date_end
                        else ""
                    ),
                    "first_contract_date": first_date or (contract.date_start.isoformat() if contract.date_start else ""),
                    "currency": currency,
                    "basic_wage": round(basic_wage, 2),
                    "allowances": allowances,
                    "total_allowances": total_allowances,
                    "total_salary": total_salary,
                    "notes": str(contract.notes or "") if "notes" in contract._fields else "",
                }

        # Fallback for Odoo 19/20 (where hr.contract was merged into hr.version / hr.employee)
        basic_wage = 0.0
        date_start = first_date
        date_end = ""
        struct_name = ""
        contract_type = ""
        schedule_pay = "monthly"
        if "wage" in employee._fields and employee.wage:
            basic_wage = float(employee.wage or 0.0)
        if "contract_date_start" in employee._fields and employee.contract_date_start:
            date_start = employee.contract_date_start.isoformat()
        if "contract_date_end" in employee._fields and employee.contract_date_end:
            date_end = employee.contract_date_end.isoformat()
        if "structure_type_id" in employee._fields and employee.structure_type_id:
            struct_name = employee.structure_type_id.name or ""
        if "contract_type_id" in employee._fields and employee.contract_type_id:
            contract_type = employee.contract_type_id.name or ""
        return {
            "has_contract": bool(basic_wage > 0 or date_start),
            "id": employee.id,
            "name": employee.name or "",
            "state": "open" if (basic_wage > 0 or date_start) else "none",
            "employee_name": employee.name or "",
            "employee_number": self.login_identifier or "",
            "job_title": employee.job_title or (employee.job_id.name if employee.job_id else ""),
            "department": employee.department_id.name if employee.department_id else "",
            "contract_type": contract_type,
            "structure_name": struct_name,
            "working_schedule": employee.resource_calendar_id.name if employee.resource_calendar_id else "",
            "schedule_pay": schedule_pay,
            "date_start": date_start,
            "date_end": date_end,
            "trial_date_end": "",
            "first_contract_date": first_date or date_start,
            "currency": currency,
            "basic_wage": round(basic_wage, 2),
            "allowances": [],
            "total_allowances": 0.0,
            "total_salary": round(basic_wage, 2),
            "notes": "",
        }


class HrEmployeeMobileApprovers(models.Model):
    _inherit = "hr.employee"

    def _ensure_approver_user_groups(self, users):
        """Ensure users selected as employee managers/approvers have Odoo approver groups."""
        if not users:
            return
        group_xmlids = (
            "hr_expense.group_hr_expense_team_approver",
            "hr_holidays.group_hr_holidays_responsible",
            "hr_attendance.group_hr_attendance_officer",
        )
        for xmlid in group_xmlids:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                for user in users.sudo():
                    if not user.share and group not in user.groups_id:
                        user.write({"groups_id": [(4, group.id)]})

    def _sync_approvers_from_parent(self):
        for emp in self.sudo():
            manager_user = emp.parent_id.user_id if emp.parent_id else False
            if not manager_user:
                continue
            self._ensure_approver_user_groups(manager_user)
            updates = {}
            for field_name in ("expense_manager_id", "leave_manager_id", "attendance_manager_id"):
                if field_name in emp._fields and not emp[field_name]:
                    updates[field_name] = manager_user.id
            if updates:
                super(HrEmployeeMobileApprovers, emp).write(updates)

    @api.onchange("parent_id")
    def _onchange_parent_sync_mobile_approvers(self):
        for emp in self:
            manager_user = emp.parent_id.user_id if emp.parent_id else False
            if not manager_user:
                continue
            for field_name in ("expense_manager_id", "leave_manager_id", "attendance_manager_id"):
                if field_name in emp._fields and not emp[field_name]:
                    emp[field_name] = manager_user

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_approvers_from_parent()
        approver_users = self.env["res.users"]
        for rec in records.sudo():
            for fname in ("expense_manager_id", "leave_manager_id", "attendance_manager_id"):
                if fname in rec._fields and rec[fname]:
                    approver_users |= rec[fname]
        self._ensure_approver_user_groups(approver_users)
        return records

    def write(self, vals):
        approver_user_ids = []
        for fname in ("expense_manager_id", "leave_manager_id", "attendance_manager_id"):
            if vals.get(fname):
                approver_user_ids.append(vals[fname])
        if vals.get("parent_id"):
            parent = self.env["hr.employee"].sudo().browse(vals["parent_id"])
            if parent.user_id:
                approver_user_ids.append(parent.user_id.id)
        if approver_user_ids:
            self._ensure_approver_user_groups(
                self.env["res.users"].sudo().browse(list(set(approver_user_ids)))
            )
        res = super().write(vals)
        if "parent_id" in vals:
            self._sync_approvers_from_parent()
        return res

    def _get_mobile_approver_employee(self, approver_field=None):
        """Return the hr.employee responsible for approving this employee's request."""
        self.ensure_one()
        emp = self.sudo()
        if approver_field and approver_field in emp._fields:
            approver_user = emp[approver_field]
            if approver_user:
                mgr_emp = approver_user.employee_id or self.env["hr.employee"].sudo().search(
                    [("user_id", "=", approver_user.id)], limit=1
                )
                if mgr_emp and mgr_emp != emp:
                    return mgr_emp
        if emp.parent_id and emp.parent_id != emp:
            return emp.parent_id
        return self.env["hr.employee"]

    def _is_mobile_approver(self, manager_employee, approver_field=None):
        """Return True if manager_employee is authorized to review this employee's request."""
        self.ensure_one()
        if not manager_employee or self == manager_employee:
            return False
        emp = self.sudo()
        mgr = manager_employee.sudo()
        if emp.parent_id == mgr:
            return True
        if approver_field and approver_field in emp._fields:
            approver_user = emp[approver_field]
            if approver_user and mgr.user_id == approver_user:
                return True
        designated = self._get_mobile_approver_employee(approver_field)
        return bool(designated and designated == mgr)

    def _mobile_team_domain(self, approver_field=None):
        """Return an hr.employee domain for employees managed/approved by `self`."""
        self.ensure_one()
        mgr = self.sudo()
        if mgr.user_id and approver_field and approver_field in self._fields:
            return [
                "&",
                ("id", "!=", mgr.id),
                "|",
                ("parent_id", "=", mgr.id),
                (approver_field, "=", mgr.user_id.id),
            ]
        return [("parent_id", "=", mgr.id), ("id", "!=", mgr.id)]

    def _is_any_mobile_manager(self):
        self.ensure_one()
        mgr = self.sudo()
        Employee = self.env["hr.employee"].sudo()
        if Employee.search_count([("parent_id", "=", mgr.id), ("id", "!=", mgr.id)]):
            return True
        if mgr.user_id:
            for fname in ("expense_manager_id", "leave_manager_id", "attendance_manager_id"):
                if fname in Employee._fields and Employee.search_count(
                    [(fname, "=", mgr.user_id.id), ("id", "!=", mgr.id)]
                ):
                    return True
        return False
