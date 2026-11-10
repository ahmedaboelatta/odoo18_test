import json
from datetime import datetime, timedelta, timezone

from odoo import fields, http
from odoo.exceptions import AccessDenied, ValidationError
from odoo.http import request

from odoo.addons.hader_mobile_core.controllers.api_v1 import API_PREFIX, HaderMobileApiV1, api_routes
from odoo.addons.hader_mobile_attendance.models.attendance import AttendanceDenied


class HaderAttendanceApiV1(http.Controller):
    @staticmethod
    def _api_datetime(value):
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _session_or_error(request_id):
        try:
            return HaderMobileApiV1._authenticated_session(), None
        except AccessDenied:
            return None, HaderMobileApiV1._response(
                status="error", error={"code": "authentication_required", "message": "Authentication required."},
                code=401, request_id=request_id,
            )

    @http.route(api_routes("/attendance/today"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def today(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        identity = session.identity_id.sudo()
        employee = identity.employee_id
        now = fields.Datetime.now()
        assignment = request.env["hader.attendance.event"]._active_assignment(employee, now.date())
        open_attendance = request.env["hr.attendance"].sudo().search(
            [("employee_id", "=", employee.id), ("check_out", "=", False)], limit=1, order="check_in desc"
        )
        device = session.device_id
        data = {
            "state": "checked_in" if open_attendance else "checked_out",
            "eligible": bool(assignment and assignment.policy_id.allow_mobile_punch),
            "mode": assignment.policy_id.attendance_mode if assignment else None,
            "requires_location": bool(assignment and assignment.policy_id.require_geofence and assignment.policy_id.attendance_mode == "on_site"),
            "maximum_accuracy_m": assignment.policy_id.maximum_accuracy_m if assignment else None,
            "open_check_in": open_attendance.check_in.isoformat() if open_attendance else None,
            "verification_required": True,
            "verification_policy": identity.verification_policy or "face",
            "face_enrolled": bool(identity.reference_face_image),
            "requires_alternative_pin": bool(identity.alternative_pin),
            "exemption_reason": identity.exemption_reason or "",
            "trusted_device": bool(device and device.trusted and not device.revoked_at),
            "device_name": device.name if device else "",
            "shift": {
                "start_hour": assignment.policy_id.shift_start_hour,
                "end_hour": assignment.policy_id.shift_end_hour,
                "timezone": assignment.policy_id.timezone,
            } if assignment else None,
        }
        return HaderMobileApiV1._response(data=data, request_id=request_id)

    @http.route(api_routes("/attendance/check-in", "/attendance/check-out"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def punch(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        operation = "check_in" if request.httprequest.path.endswith("check-in") else "check_out"
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            event, duplicate = request.env["hader.attendance.event"].mobile_punch(session, operation, payload)
        except json.JSONDecodeError:
            return HaderMobileApiV1._response(status="error", error={"code": "invalid_json", "message": "Invalid JSON body."}, code=422, request_id=request_id)
        except AttendanceDenied as exc:
            return HaderMobileApiV1._response(status="error", error={"code": exc.code, "message": str(exc)}, code=403, request_id=request_id)
        except AccessDenied:
            return HaderMobileApiV1._response(status="error", error={"code": "attendance_not_permitted", "message": "Attendance is not permitted."}, code=403, request_id=request_id)
        except ValidationError as exc:
            return HaderMobileApiV1._response(status="error", error={"code": "attendance_validation_failed", "message": str(exc)}, code=422, request_id=request_id)
        return HaderMobileApiV1._response(
            data={**event.receipt_dto(), "duplicate": duplicate}, code=200 if duplicate else 201, request_id=request_id
        )

    @http.route(api_routes("/attendance/history"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def history(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        domain = [("employee_id", "=", session.identity_id.employee_id.id)]
        args = request.httprequest.args
        date_from_str = (args.get("date_from") or "").strip()
        date_to_str = (args.get("date_to") or "").strip()
        try:
            if date_from_str:
                dt_from = datetime.strptime(date_from_str[:10], "%Y-%m-%d") - timedelta(hours=5)
                domain.append(("check_in", ">=", dt_from))
            if date_to_str:
                dt_to = datetime.strptime(date_to_str[:10], "%Y-%m-%d") + timedelta(days=1, hours=5)
                domain.append(("check_in", "<=", dt_to))
            if not date_from_str and not date_to_str:
                dt_default = fields.Datetime.now() - timedelta(days=10)
                domain.append(("check_in", ">=", dt_default))
        except ValueError:
            pass
        rows = request.env["hader.attendance.report"].sudo().search(
            domain, limit=200, order="check_in desc, id desc"
        )
        return HaderMobileApiV1._response(data={"items": [row.history_dto() for row in rows]}, request_id=request_id)

    @http.route(api_routes("/attendance/corrections"), type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def corrections(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        Correction = request.env["hader.attendance.correction"].sudo()
        if request.httprequest.method == "GET":
            rows = Correction.search([("employee_id", "=", employee.id)], limit=50, order="create_date desc, id desc")
            return HaderMobileApiV1._response(data={"items": [row.mobile_dto() for row in rows]}, request_id=request_id)
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
            partner = employee.work_contact_id
            correction.message_post(
                body=f"Mobile correction request submitted by {employee.name}.",
                author_id=partner.id if partner else None,
                message_type="comment", subtype_xmlid="mail.mt_note",
            )
            request.env["hader.mobile.audit"].sudo().create({
                "identity_id": session.identity_id.id,
                "company_id": employee.company_id.id,
                "event_type": "attendance_correction_submitted",
                "request_id": request_id,
                "outcome": "success",
                "metadata_json": json.dumps({
                    "employee_id": employee.id, "employee_name": employee.name,
                    "correction_id": correction.id,
                }, ensure_ascii=False),
            })
            manager = (
                employee._get_mobile_approver_employee("attendance_manager_id")
                if hasattr(employee, "_get_mobile_approver_employee")
                else employee.parent_id
            )
            if manager and "hader.mobile.notification.inbox" in request.env:
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    manager,
                    "طلب تصحيح حضور جديد",
                    f"أرسل {employee.name} طلب تصحيح حضور ({reason}).",
                    "correction_submitted",
                    title_en="New attendance correction request",
                    body_en=f"{employee.name} submitted an attendance correction request ({reason}).",
                )
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error", error={"code": "correction_validation_failed", "message": str(exc)},
                code=422, request_id=request_id,
            )
        return HaderMobileApiV1._response(data=correction.mobile_dto(), code=201, request_id=request_id)

    @http.route(api_routes("/attendance/corrections/team"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def team_corrections(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        emp_domain = (
            manager._mobile_team_domain("attendance_manager_id")
            if hasattr(manager, "_mobile_team_domain")
            else [("parent_id", "=", manager.id), ("id", "!=", manager.id)]
        )
        team_emp_ids = request.env["hr.employee"].sudo().search(
            emp_domain + [("company_id", "=", manager.company_id.id)]
        ).ids
        rows = request.env["hader.attendance.correction"].sudo().search([
            ("employee_id", "in", team_emp_ids),
        ], limit=50, order="state asc, create_date desc, id desc")
        return HaderMobileApiV1._response(
            data={"items": [row.mobile_dto() for row in rows]}, request_id=request_id
        )

    @http.route(api_routes("/attendance/corrections/<int:correction_id>/review"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def review_correction(self, correction_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        correction = request.env["hader.attendance.correction"].sudo().browse(correction_id).exists()
        is_allowed = bool(
            correction
            and correction.employee_id != manager
            and (
                (
                    hasattr(correction.employee_id, "_is_mobile_approver")
                    and correction.employee_id._is_mobile_approver(manager, "attendance_manager_id")
                )
                or correction.employee_id.parent_id == manager
            )
        )
        if not is_allowed:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "correction_not_found", "message": "Correction request not found."},
                code=404,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            decision = str(payload.get("decision") or "").strip()
            note = str(payload.get("note") or "").strip()
            correction.mobile_review(manager, decision, note)
            request.env["hader.mobile.audit"].sudo().create({
                "identity_id": session.identity_id.id,
                "company_id": manager.company_id.id,
                "event_type": "attendance_correction_reviewed",
                "request_id": request_id,
                "outcome": "success",
                "metadata_json": json.dumps({
                    "manager_id": manager.id, "manager_name": manager.name,
                    "employee_id": correction.employee_id.id,
                    "employee_name": correction.employee_id.name,
                    "correction_id": correction.id,
                    "decision": decision,
                }, ensure_ascii=False),
            })
            if "hader.mobile.notification.inbox" in request.env:
                approved = decision == "approve"
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    correction.employee_id,
                    "تم قبول تصحيح الحضور" if approved else "تم رفض تصحيح الحضور",
                    "تم اعتماد طلب تصحيح الحضور الخاص بك." if approved else f"تم رفض طلب تصحيح الحضور. السبب: {note}",
                    "correction_result",
                    title_en="Attendance correction approved" if approved else "Attendance correction rejected",
                    body_en="Your attendance correction request was approved." if approved else f"Rejection reason: {note}",
                )
        except (json.JSONDecodeError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "correction_review_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(data=correction.mobile_dto(), request_id=request_id)
