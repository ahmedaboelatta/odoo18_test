import math
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, ValidationError


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
        [("device_location", "Device and location")], required=True, default="device_location", readonly=True
    )
    review_state = fields.Selection(
        [("accepted", "Accepted"), ("review", "Needs review"), ("rejected", "Rejected")],
        required=True,
        default="accepted",
        readonly=True,
    )

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
            raise AccessDenied()
        policy = assignment.policy_id
        mode = payload.get("attendance_mode", "on_site")
        if mode != policy.attendance_mode and policy.attendance_mode != "hybrid":
            raise AccessDenied()
        if accuracy > policy.maximum_accuracy_m:
            raise ValidationError(_("Location accuracy is too low. Please retry outdoors."))
        location = self.env["alezdhar.work.location"]
        distance = 0.0
        outcome = "not_required"
        if policy.require_geofence:
            eligible = assignment.location_ids.filtered("active")
            if not eligible:
                raise AccessDenied()
            candidates = [(loc, self._distance_m(latitude, longitude, loc.latitude, loc.longitude)) for loc in eligible]
            location, distance = min(candidates, key=lambda item: item[1])
            if accuracy > location.maximum_accuracy_m:
                raise ValidationError(_("Location accuracy exceeds the selected work location policy."))
            if distance > location.radius_m:
                raise AccessDenied()
            outcome = "inside"
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", [employee.id])
        open_attendance = self.env["hr.attendance"].sudo().search(
            [("employee_id", "=", employee.id), ("check_out", "=", False)], order="check_in desc", limit=1
        )
        if operation == "check_in":
            if open_attendance:
                raise ValidationError(_("The employee is already checked in."))
            attendance = self.env["hr.attendance"].sudo().create({"employee_id": employee.id, "check_in": now})
        else:
            if not open_attendance:
                raise ValidationError(_("There is no open attendance to check out."))
            open_attendance.sudo().write({"check_out": now})
            attendance = open_attendance
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
            "geofence_outcome": outcome, "review_state": "accepted",
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
        }
