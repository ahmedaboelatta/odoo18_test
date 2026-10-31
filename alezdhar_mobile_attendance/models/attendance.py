import base64
import binascii
import io
import math
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps, UnidentifiedImageError

from odoo import _, api, fields, models, tools
from odoo.exceptions import AccessDenied, ValidationError


class AttendanceDenied(AccessDenied):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class AlezdharAttendanceEvent(models.Model):
    _name = "alezdhar.attendance.event"
    _description = "Alezdhar Attendance Event"
    _order = "server_time desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    identity_id = fields.Many2one("alezdhar.mobile.identity", required=True, index=True, ondelete="restrict")
    device_id = fields.Many2one("alezdhar.mobile.device", required=True, index=True, ondelete="restrict")
    attendance_id = fields.Many2one("hr.attendance", index=True, ondelete="set null")
    location_id = fields.Many2one("alezdhar.work.location", index=True, ondelete="restrict")
    policy_id = fields.Many2one("alezdhar.attendance.policy", required=True, ondelete="restrict")
    request_id = fields.Char(required=True, index=True, copy=False)
    operation = fields.Selection([("check_in", "Check in"), ("check_out", "Check out")], required=True, index=True)
    server_time = fields.Datetime(required=True, readonly=True, index=True)
    captured_at = fields.Datetime(readonly=True)
    latitude = fields.Float(required=True, digits=(10, 7), readonly=True)
    longitude = fields.Float(required=True, digits=(10, 7), readonly=True)
    accuracy_m = fields.Float(required=True, readonly=True)
    distance_m = fields.Float(readonly=True)
    attendance_mode = fields.Selection(
        [("on_site", "On site"), ("remote", "Remote"), ("hybrid", "Hybrid"), ("field", "Field")],
        required=True,
        readonly=True,
    )
    geofence_outcome = fields.Selection(
        [("inside", "Inside"), ("not_required", "Not required")], required=True, readonly=True
    )
    verification_method = fields.Selection(
        [
            ("device_location", "Device and location"),
            ("face_biometric", "Face verification (بصمة الوجه)"),
            ("alternative_exemption", "Alternative verification - Exempted (تحقق بديل - إعفاء معتمد)"),
        ],
        required=True,
        default="device_location",
        readonly=True,
    )
    selfie_image = fields.Binary(
        string="Attendance Selfie",
        attachment=True,
        readonly=True,
        groups="alezdhar_mobile_core.group_mobile_auditor",
    )
    face_match_score = fields.Float(
        string="Face Match Score (%)",
        readonly=True,
    )
    liveness_verified = fields.Boolean(
        string="Liveness Verified",
        readonly=True,
    )
    review_state = fields.Selection(
        [("accepted", "Accepted"), ("review", "Needs review"), ("rejected", "Rejected")],
        required=True,
        default="accepted",
        readonly=True,
    )
    attendance_check_in = fields.Datetime(related="attendance_id.check_in", readonly=True)
    attendance_check_out = fields.Datetime(related="attendance_id.check_out", readonly=True)
    worked_hours = fields.Float(related="attendance_id.worked_hours", readonly=True)
    punctuality_status = fields.Selection(
        [("on_time", "On time"), ("late", "Late"), ("early_leave", "Early leave"), ("normal", "Normal")],
        required=True,
        default="normal",
        readonly=True,
    )
    variance_minutes = fields.Integer(readonly=True)
    expected_hours = fields.Float(readonly=True)

    _sql_constraints = [("request_id_unique", "UNIQUE(request_id)", "Attendance request id must be unique.")]

    def write(self, vals):
        if not self.env.su:
            raise AccessDenied()
        return super().write(vals)

    def unlink(self):
        raise AccessDenied()

    @staticmethod
    def _distance_m(lat1, lon1, lat2, lon2):
        radius = 6371000.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

    @api.model
    def _active_assignment(self, employee, on_date):
        return self.env["alezdhar.employee.attendance.assignment"].sudo().search(
            [("employee_id", "=", employee.id), ("active", "=", True),
             ("date_from", "<=", on_date), "|", ("date_to", "=", False), ("date_to", ">=", on_date)],
            order="date_from desc, id desc", limit=1,
        )

    @staticmethod
    def _hour_parts(value):
        hour = int(value)
        minute = int(round((value - hour) * 60))
        if minute == 60:
            hour = (hour + 1) % 24
            minute = 0
        return hour, minute

    @api.model
    def _shift_bounds(self, policy, server_time, attendance=None):
        tz = ZoneInfo(policy.timezone)
        utc_time = fields.Datetime.to_datetime(server_time).replace(tzinfo=timezone.utc)
        local_time = utc_time.astimezone(tz)
        shift_date = local_time.date()
        if attendance and attendance.check_in:
            check_in_utc = fields.Datetime.to_datetime(attendance.check_in).replace(tzinfo=timezone.utc)
            shift_date = check_in_utc.astimezone(tz).date()
        start_hour, start_minute = self._hour_parts(policy.shift_start_hour)
        end_hour, end_minute = self._hour_parts(policy.shift_end_hour)
        start = datetime.combine(shift_date, time(start_hour, start_minute), tzinfo=tz)
        end = datetime.combine(shift_date, time(end_hour, end_minute), tzinfo=tz)
        if end <= start:
            end += timedelta(days=1)
        return local_time, start, end

    @api.model
    def _punctuality(self, policy, operation, server_time, attendance=None):
        local_time, start, end = self._shift_bounds(policy, server_time, attendance)
        if operation == "check_in":
            late_after = start + timedelta(minutes=policy.late_grace_minutes)
            if local_time > late_after:
                return "late", max(1, int((local_time - start).total_seconds() // 60))
            return "on_time", 0
        early_before = end - timedelta(minutes=policy.early_leave_grace_minutes)
        if local_time < early_before:
            return "early_leave", max(1, int((end - local_time).total_seconds() // 60))
        return "normal", 0

    @staticmethod
    def _extract_face_signature(raw_bytes):
        with Image.open(io.BytesIO(raw_bytes)) as img:
            gray = ImageOps.exif_transpose(img).convert("L")
            w, h = gray.size
            if w < 48 or h < 48:
                raise ValueError("Image too small")
            # Crop central region focusing on the face inside the oval frame
            margin_x = int(w * 0.14)
            margin_y = int(h * 0.14)
            cropped = gray.crop((margin_x, margin_y, w - margin_x, h - margin_y))
            equalized = ImageOps.equalize(cropped)
            small = equalized.resize((12, 12))
            pixels = list(small.getdata())
            mean = sum(pixels) / len(pixels)
            variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
            if variance < 5.0:
                raise ValueError("Blank or uniform image")
            std = math.sqrt(variance) or 1.0
            return [(p - mean) / std for p in pixels]

    @classmethod
    def _compare_face_images(cls, ref_b64, selfie_bytes):
        if isinstance(ref_b64, str):
            ref_bytes = base64.b64decode(ref_b64)
        else:
            ref_bytes = base64.b64decode(ref_b64 or b"")
        sig1 = cls._extract_face_signature(ref_bytes)
        sig2 = cls._extract_face_signature(selfie_bytes)
        mad = sum(abs(a - b) for a, b in zip(sig1, sig2)) / len(sig1)
        # Normalized z-score MAD typically ranges 0.0 (identical) to ~1.4 (uncorrelated)
        score = max(0.0, min(100.0, (1.0 - (mad / 2.2)) * 100.0))
        return round(score, 1)

    @api.model
    def _verify_identity_for_punch(self, session, policy, payload):
        device = session.device_id
        if not device or not device.trusted or device.revoked_at:
            raise AttendanceDenied(
                "untrusted_device",
                _("هذا الجهاز غير موثوق لتسجيل البصمة. / This device is not trusted for attendance."),
            )
        identity = session.identity_id.sudo()
        requested_method = payload.get("verification_method")
        enforce_biometric = (
            policy.biometric_provider == "face_or_alternative"
            or requested_method in ("face_biometric", "alternative_exemption")
            or bool(payload.get("selfie_base64"))
        )
        if not enforce_biometric:
            return "device_location", False, 0.0, False

        if identity.verification_policy == "alternative":
            if identity.alternative_pin:
                supplied_pin = str(payload.get("alternative_pin") or "").strip()
                if supplied_pin != identity.alternative_pin:
                    raise AttendanceDenied(
                        "invalid_alternative_pin",
                        _("رمز التحقق البديل غير صحيح. / Invalid alternative verification PIN."),
                    )
            return "alternative_exemption", False, 100.0, False

        # Face verification policy
        raw_selfie = str(payload.get("selfie_base64") or "").strip()
        if "," in raw_selfie and raw_selfie.startswith("data:"):
            raw_selfie = raw_selfie.split(",", 1)[1]
        if not raw_selfie:
            raise AttendanceDenied(
                "face_verification_required",
                _("يرجى التقاط صورة الوجه (السيلفي) للتحقق من الهوية قبل تسجيل البصمة. / Face selfie verification is required before punching."),
            )
        if not identity.reference_face_image:
            if payload.get("enroll_if_missing"):
                identity.enroll_reference_face(raw_selfie)
            else:
                raise AttendanceDenied(
                    "face_not_enrolled",
                    _("يرجى إتمام التفعيل الأول وتسجيل الصورة المرجعية للوجه أولاً. / Please enroll your reference face photo first."),
                )
        try:
            selfie_bytes = base64.b64decode(raw_selfie, validate=True)
            if not selfie_bytes or len(selfie_bytes) > 5 * 1024 * 1024:
                raise ValueError("Invalid selfie size")
            score = self._compare_face_images(identity.reference_face_image, selfie_bytes)
        except (binascii.Error, UnidentifiedImageError, OSError, ValueError):
            raise AttendanceDenied(
                "face_mismatch",
                _("الصورة الملتقطة غير واضحة. يرجى النظر للكاميرا في إضاءة جيدة والمحاولة مرة أخرى. / Captured selfie is not clear. Please look at the camera in good lighting."),
            )
        if score < 38.0:
            raise AttendanceDenied(
                "face_mismatch",
                _("لم تتطابق بصمة الوجه مع الصورة المرجعية المسجلة. يرجى المحاولة مرة أخرى في إضاءة واضحة أو تحديث الصورة المرجعية من الملف الشخصي. / Face verification did not match the enrolled reference photo."),
            )
        with Image.open(io.BytesIO(selfie_bytes)) as img:
            rgb = img.convert("RGB")
            rgb.thumbnail((480, 480))
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=82)
            normalized_selfie_b64 = base64.b64encode(out.getvalue()).decode("ascii")
        liveness_ok = bool(payload.get("liveness_passed", True))
        return "face_biometric", normalized_selfie_b64, score, liveness_ok

    @api.model
    def mobile_punch(self, session, operation, payload):
        if operation not in ("check_in", "check_out") or not isinstance(payload, dict):
            raise ValidationError(_("Invalid attendance operation."))
        identity = session.identity_id
        identity._assert_can_authenticate()
        employee = identity.employee_id
        if employee.company_id != session.company_id:
            raise AccessDenied()
        try:
            request_id = str(uuid.UUID(str(payload.get("request_id", ""))))
            latitude = float(payload["latitude"])
            longitude = float(payload["longitude"])
            accuracy = float(payload["accuracy_m"])
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ValidationError(_("A valid request id, location and accuracy are required."))
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or accuracy <= 0:
            raise ValidationError(_("Location coordinates or accuracy are invalid."))
        duplicate = self.sudo().search([("request_id", "=", request_id)], limit=1)
        if duplicate:
            return duplicate, True
        now = fields.Datetime.now()
        assignment = self._active_assignment(employee, now.date())
        if not assignment or not assignment.policy_id.allow_mobile_punch:
            raise AttendanceDenied("attendance_not_assigned", _("No active attendance assignment was found."))
        policy = assignment.policy_id
        mode = payload.get("attendance_mode", "on_site")
        if mode != policy.attendance_mode and policy.attendance_mode != "hybrid":
            raise AttendanceDenied("attendance_mode_not_allowed", _("Attendance mode is not allowed."))
        if accuracy > policy.maximum_accuracy_m:
            raise ValidationError(
                _("دقة تحديد الموقع الحالية (%.0f متر) أضعف من الحد المسموح (%.0f متر). يرجى التحديث والمحاولة مرة أخرى.")
                % (accuracy, policy.maximum_accuracy_m)
            )
        location = self.env["alezdhar.work.location"]
        distance = 0.0
        outcome = "not_required"
        if policy.require_geofence and mode == "on_site":
            eligible = assignment.location_ids.filtered("active")
            if not eligible:
                raise AttendanceDenied("attendance_location_missing", _("No eligible work location was found."))
            candidates = [(loc, self._distance_m(latitude, longitude, loc.latitude, loc.longitude)) for loc in eligible]
            location, distance = min(candidates, key=lambda item: item[1])
            if accuracy > location.maximum_accuracy_m:
                raise ValidationError(
                    _("دقة تحديد الموقع الحالية (%.0f متر) تتجاوز الحد المسموح لموقع العمل (%.0f متر). يرجى إعادة تحديد الموقع.")
                    % (accuracy, location.maximum_accuracy_m)
                )
            if distance > location.radius_m:
                raise AttendanceDenied("outside_geofence", _("Current location is outside the permitted work area."))
            outcome = "inside"
        verification_method, selfie_b64, match_score, liveness_ok = self._verify_identity_for_punch(
            session, policy, payload
        )
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", [employee.id])
        open_attendance = self.env["hr.attendance"].sudo().search(
            [("employee_id", "=", employee.id), ("check_out", "=", False)], order="check_in desc", limit=1
        )
        if operation == "check_in":
            if open_attendance:
                raise ValidationError(_("تم تسجيل حضورك بالفعل، لا يمكن تسجيل الحضور مرتين متتاليتين."))
            attendance = self.env["hr.attendance"].sudo().create({"employee_id": employee.id, "check_in": now})
        else:
            if not open_attendance:
                raise ValidationError(_("لا يوجد تسجيل حضور مفتوح حالياً لتسجيل الانصراف."))
            open_attendance.sudo().write({"check_out": now})
            attendance = open_attendance
        punctuality_status, variance_minutes = self._punctuality(
            policy, operation, now, attendance=attendance
        )
        expected_hours = (
            policy.shift_end_hour - policy.shift_start_hour
            if policy.shift_end_hour > policy.shift_start_hour
            else 24.0 - policy.shift_start_hour + policy.shift_end_hour
        )
        captured_at = payload.get("captured_at")
        try:
            captured_at = fields.Datetime.to_datetime(captured_at) if captured_at else False
        except (TypeError, ValueError):
            captured_at = False
        event = self.sudo().create({
            "employee_id": employee.id, "identity_id": identity.id, "device_id": session.device_id.id,
            "attendance_id": attendance.id, "location_id": location.id, "policy_id": policy.id,
            "request_id": request_id, "operation": operation, "server_time": now,
            "captured_at": captured_at, "latitude": latitude, "longitude": longitude,
            "accuracy_m": accuracy, "distance_m": distance, "attendance_mode": mode,
            "geofence_outcome": outcome,
            "verification_method": verification_method,
            "selfie_image": selfie_b64,
            "face_match_score": match_score,
            "liveness_verified": liveness_ok,
            "review_state": "accepted",
            "punctuality_status": punctuality_status,
            "variance_minutes": variance_minutes,
            "expected_hours": expected_hours,
        })
        return event, False

    def receipt_dto(self):
        self.ensure_one()
        return {
            "event_ref": self.id,
            "operation": self.operation,
            "server_time": self.server_time.isoformat(),
            "attendance_state": "checked_in" if not self.attendance_id.check_out else "checked_out",
            "location": self.location_id.name if self.location_id else None,
            "distance_m": round(self.distance_m, 1),
            "geofence": self.geofence_outcome,
            "verification_method": self.verification_method,
            "face_match_score": round(self.face_match_score or 0.0, 1),
            "check_in": self.attendance_id.check_in.isoformat() if self.attendance_id.check_in else None,
            "check_out": self.attendance_id.check_out.isoformat() if self.attendance_id.check_out else None,
            "worked_minutes": round(self.attendance_id.worked_hours * 60),
            "punctuality_status": self.punctuality_status,
            "variance_minutes": self.variance_minutes,
        }


class AlezdharAttendanceReport(models.Model):
    _name = "alezdhar.attendance.report"
    _description = "Alezdhar Attendance Report"
    _auto = False
    _order = "check_in desc, id desc"

    employee_id = fields.Many2one("hr.employee", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    check_in = fields.Datetime(readonly=True)
    check_out = fields.Datetime(readonly=True)
    worked_hours = fields.Float(readonly=True)
    expected_hours = fields.Float(readonly=True)
    overtime_hours = fields.Float(readonly=True)
    late_minutes = fields.Integer(readonly=True)
    early_leave_minutes = fields.Integer(readonly=True)
    policy_id = fields.Many2one("alezdhar.attendance.policy", readonly=True)
    location_id = fields.Many2one("alezdhar.work.location", readonly=True)
    attendance_mode = fields.Selection(
        [("on_site", "On site"), ("remote", "Remote"), ("hybrid", "Hybrid"), ("field", "Field")],
        readonly=True,
    )
    event_ids = fields.Many2many(
        "alezdhar.attendance.event", compute="_compute_event_ids", string="Attendance logs", readonly=True
    )

    def _compute_event_ids(self):
        events = self.env["alezdhar.attendance.event"].sudo().search(
            [("attendance_id", "in", self.ids)], order="server_time, id"
        ) if self.ids else self.env["alezdhar.attendance.event"]
        grouped = {}
        for event in events:
            grouped.setdefault(event.attendance_id.id, self.env["alezdhar.attendance.event"])
            grouped[event.attendance_id.id] |= event
        for record in self:
            record.event_ids = grouped.get(record.id, self.env["alezdhar.attendance.event"])

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW alezdhar_attendance_report AS (
                SELECT
                    a.id,
                    a.employee_id,
                    e.company_id,
                    a.check_in,
                    a.check_out,
                    COALESCE(a.worked_hours, 0.0) AS worked_hours,
                    COALESCE(ev.expected_hours, a.expected_hours, 0.0) AS expected_hours,
                    GREATEST(COALESCE(a.worked_hours, 0.0) - COALESCE(ev.expected_hours, a.expected_hours, 0.0), 0.0) AS overtime_hours,
                    COALESCE(ev.late_minutes, 0) AS late_minutes,
                    COALESCE(ev.early_leave_minutes, 0) AS early_leave_minutes,
                    ev.policy_id,
                    ev.location_id,
                    ev.attendance_mode
                FROM hr_attendance a
                JOIN hr_employee e ON e.id = a.employee_id
                LEFT JOIN LATERAL (
                    SELECT
                        MAX(x.policy_id) AS policy_id,
                        MAX(x.location_id) AS location_id,
                        MAX(x.attendance_mode) AS attendance_mode,
                        MAX(CASE WHEN x.punctuality_status = 'late' THEN x.variance_minutes ELSE 0 END) AS late_minutes,
                        MAX(CASE WHEN x.punctuality_status = 'early_leave' THEN x.variance_minutes ELSE 0 END) AS early_leave_minutes,
                        MAX(x.expected_hours) AS expected_hours
                    FROM alezdhar_attendance_event x
                    WHERE x.attendance_id = a.id
                ) ev ON TRUE
                WHERE ev.policy_id IS NOT NULL
            )
        """)

    def history_dto(self):
        self.ensure_one()
        return {
            "attendance_ref": self.id,
            "operation": "check_out" if self.check_out else "check_in",
            "server_time": (self.check_out or self.check_in).isoformat(),
            "check_in": self.check_in.isoformat() if self.check_in else None,
            "check_out": self.check_out.isoformat() if self.check_out else None,
            "worked_minutes": round(self.worked_hours * 60),
            "overtime_minutes": round(self.overtime_hours * 60),
            "late_minutes": self.late_minutes,
            "early_leave_minutes": self.early_leave_minutes,
            "punctuality_status": "late" if self.late_minutes else ("early_leave" if self.early_leave_minutes else "normal"),
            "variance_minutes": self.late_minutes or self.early_leave_minutes,
            "attendance_mode": self.attendance_mode,
        }
