import json
from datetime import datetime, timezone

from odoo import fields, http
from odoo.exceptions import AccessDenied, ValidationError
from odoo.http import request

from odoo.addons.alezdhar_mobile_core.controllers.api_v1 import API_PREFIX, AlezdharMobileApiV1
from odoo.addons.alezdhar_mobile_attendance.models.attendance import AttendanceDenied


class AlezdharAttendanceApiV1(http.Controller):
    @staticmethod
    def _api_datetime(value):
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _session_or_error(request_id):
        try:
            return AlezdharMobileApiV1._authenticated_session(), None
        except AccessDenied:
            return None, AlezdharMobileApiV1._response(
                status="error", error={"code": "authentication_required", "message": "Authentication required."},
                code=401, request_id=request_id,
            )

    @http.route(API_PREFIX + "/attendance/today", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def today(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        now = fields.Datetime.now()
        assignment = request.env["alezdhar.attendance.event"]._active_assignment(employee, now.date())
        open_attendance = request.env["hr.attendance"].sudo().search(
            [("employee_id", "=", employee.id), ("check_out", "=", False)], limit=1, order="check_in desc"
        )
        data = {
            "state": "checked_in" if open_attendance else "checked_out",
            "eligible": bool(assignment and assignment.policy_id.allow_mobile_punch),
            "mode": assignment.policy_id.attendance_mode if assignment else None,
            "requires_location": bool(assignment and assignment.policy_id.require_geofence and assignment.policy_id.attendance_mode == "on_site"),
            "maximum_accuracy_m": assignment.policy_id.maximum_accuracy_m if assignment else None,
            "open_check_in": open_attendance.check_in.isoformat() if open_attendance else None,
            "shift": {
                "start_hour": assignment.policy_id.shift_start_hour,
                "end_hour": assignment.policy_id.shift_end_hour,
                "timezone": assignment.policy_id.timezone,
            } if assignment else None,
        }
        return AlezdharMobileApiV1._response(data=data, request_id=request_id)

    @http.route([API_PREFIX + "/attendance/check-in", API_PREFIX + "/attendance/check-out"], type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def punch(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        operation = "check_in" if request.httprequest.path.endswith("check-in") else "check_out"
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            event, duplicate = request.env["alezdhar.attendance.event"].mobile_punch(session, operation, payload)
        except json.JSONDecodeError:
            return AlezdharMobileApiV1._response(status="error", error={"code": "invalid_json", "message": "Invalid JSON body."}, code=422, request_id=request_id)
        except AttendanceDenied as exc:
            return AlezdharMobileApiV1._response(status="error", error={"code": exc.code, "message": str(exc)}, code=403, request_id=request_id)
        except AccessDenied:
            return AlezdharMobileApiV1._response(status="error", error={"code": "attendance_not_permitted", "message": "Attendance is not permitted."}, code=403, request_id=request_id)
        except ValidationError as exc:
            return AlezdharMobileApiV1._response(status="error", error={"code": "attendance_validation_failed", "message": str(exc)}, code=422, request_id=request_id)
        return AlezdharMobileApiV1._response(
            data={**event.receipt_dto(), "duplicate": duplicate}, code=200 if duplicate else 201, request_id=request_id
        )

    @http.route(API_PREFIX + "/attendance/history", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def history(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        rows = request.env["alezdhar.attendance.report"].sudo().search(
            [("employee_id", "=", session.identity_id.employee_id.id)], limit=50, order="check_in desc, id desc"
        )
        return AlezdharMobileApiV1._response(data={"items": [row.history_dto() for row in rows]}, request_id=request_id)

    @http.route(API_PREFIX + "/attendance/corrections", type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def corrections(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        Correction = request.env["alezdhar.attendance.correction"].sudo()
        if request.httprequest.method == "GET":
            rows = Correction.search([("employee_id", "=", employee.id)], limit=50, order="create_date desc, id desc")
            return AlezdharMobileApiV1._response(data={"items": [row.mobile_dto() for row in rows]}, request_id=request_id)
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            attendance = request.env["hr.attendance"].sudo().search([
                ("id", "=", int(payload.get("attendance_ref"))), ("employee_id", "=", employee.id)
            ], limit=1)
            reason = str(payload.get("reason") or "").strip()
            requested_in = self._api_datetime(payload.get("requested_check_in"))
            requested_out = self._api_datetime(payload.get("requested_check_out")) if payload.get("requested_check_out") else False
            if not attendance or not reason or len(reason) < 5 or not requested_in:
                raise ValidationError("A valid attendance, requested time and reason are required.")
            if requested_out and requested_out <= requested_in:
                raise ValidationError("Requested check-out must be after check-in.")
            if Correction.search_count([("attendance_id", "=", attendance.id), ("state", "=", "submitted")]):
                raise ValidationError("A correction for this attendance is already under review.")
            correction = Correction.create({
                "employee_id": employee.id, "attendance_id": attendance.id,
                "requested_check_in": requested_in, "requested_check_out": requested_out,
                "reason": reason,
            })
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            return AlezdharMobileApiV1._response(
                status="error", error={"code": "correction_validation_failed", "message": str(exc)},
                code=422, request_id=request_id,
            )
        return AlezdharMobileApiV1._response(data=correction.mobile_dto(), code=201, request_id=request_id)

    @http.route(API_PREFIX + "/attendance/corrections/team", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def team_corrections(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        rows = request.env["alezdhar.attendance.correction"].sudo().search([
            ("employee_id.parent_id", "=", manager.id),
            ("employee_id", "!=", manager.id),
        ], limit=50, order="state asc, create_date desc, id desc")
        return AlezdharMobileApiV1._response(
            data={"items": [row.mobile_dto() for row in rows]}, request_id=request_id
        )

    @http.route(API_PREFIX + "/attendance/corrections/<int:correction_id>/review", type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def review_correction(self, correction_id, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        correction = request.env["alezdhar.attendance.correction"].sudo().search([
            ("id", "=", correction_id),
            ("employee_id.parent_id", "=", manager.id),
            ("employee_id", "!=", manager.id),
        ], limit=1)
        if not correction:
            return AlezdharMobileApiV1._response(
                status="error",
                error={"code": "correction_not_found", "message": "Correction request not found."},
                code=404,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            correction.mobile_review(manager, str(payload.get("decision") or ""), payload.get("note"))
        except (json.JSONDecodeError, ValidationError) as exc:
            return AlezdharMobileApiV1._response(
                status="error",
                error={"code": "correction_review_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return AlezdharMobileApiV1._response(data=correction.mobile_dto(), request_id=request_id)
