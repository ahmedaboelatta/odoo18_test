import base64
import binascii
import json
from datetime import date

from odoo import http
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.http import request

from odoo.addons.alezdhar_mobile_core.controllers.api_v1 import (
    API_PREFIX,
    AlezdharMobileApiV1,
)


class AlezdharLeaveApiV1(http.Controller):
    @staticmethod
    def _session(request_id):
        try:
            return AlezdharMobileApiV1._authenticated_session(), None
        except AccessDenied:
            return None, AlezdharMobileApiV1._response(
                status="error",
                error={"code": "authentication_required", "message": "Authentication required."},
                code=401,
                request_id=request_id,
            )

    @staticmethod
    def _leave_dto(leave):
        attachments = request.env["ir.attachment"].sudo().search([
            ("res_model", "=", "hr.leave"), ("res_id", "=", leave.id)
        ])
        return {
            "id": leave.id,
            "type_id": leave.holiday_status_id.id,
            "type_name": leave.holiday_status_id.name,
            "date_from": leave.request_date_from.isoformat(),
            "date_to": leave.request_date_to.isoformat(),
            "days": leave.number_of_days,
            "reason": leave.notes or "",
            "state": leave.state,
            "employee_name": leave.employee_id.name,
            "review_note": leave.mobile_review_note or "",
            "attachments": [{"id": item.id, "name": item.name, "mimetype": item.mimetype} for item in attachments],
        }

    @http.route(API_PREFIX + "/leave/summary", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def summary(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        LeaveType = request.env["hr.leave.type"].sudo().with_context(employee_id=employee.id)
        types = LeaveType.search([("active", "=", True), ("company_id", "in", [False, employee.company_id.id])])
        balances = [
            {
                "type_id": item.id,
                "name": item.name,
                "remaining_days": item.virtual_remaining_leaves,
                "requires_allocation": item.requires_allocation != "no",
            }
            for item in types
        ]
        pending = request.env["hr.leave"].sudo().search_count([
            ("employee_id", "=", employee.id), ("state", "in", ["confirm", "validate1"])
        ])
        return AlezdharMobileApiV1._response(data={"balances": balances, "pending_count": pending}, request_id=request_id)

    @http.route(API_PREFIX + "/leave/requests", type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def leave_requests(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        Leave = request.env["hr.leave"].sudo()
        if request.httprequest.method == "GET":
            rows = Leave.search([("employee_id", "=", employee.id)], limit=50, order="request_date_from desc, id desc")
            return AlezdharMobileApiV1._response(data={"items": [self._leave_dto(row) for row in rows]}, request_id=request_id)
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            start = date.fromisoformat(str(payload.get("date_from")))
            end = date.fromisoformat(str(payload.get("date_to")))
            reason = str(payload.get("reason") or "").strip()
            leave_type = request.env["hr.leave.type"].sudo().search([
                ("id", "=", int(payload.get("type_id"))), ("active", "=", True),
                ("company_id", "in", [False, employee.company_id.id]),
            ], limit=1)
            if not leave_type or end < start or not reason:
                raise ValidationError("A valid leave type, date range and reason are required.")
            overlap = Leave.search([
                ("employee_id", "=", employee.id),
                ("state", "not in", ["refuse", "cancel"]),
                ("request_date_from", "<=", end),
                ("request_date_to", ">=", start),
            ], limit=1)
            if overlap:
                raise ValidationError(
                    "يوجد طلب إجازة آخر متداخل مع هذه الفترة. اختر تاريخًا مختلفًا. / "
                    "Another time-off request overlaps this period. Choose different dates."
                )
            attachment = payload.get("attachment")
            attachment_values = None
            if attachment:
                name = str(attachment.get("name") or "").strip()[:255]
                mimetype = str(attachment.get("mimetype") or "application/octet-stream")[:128]
                if mimetype not in {"application/pdf", "image/jpeg", "image/png"}:
                    raise ValidationError("Only PDF, JPG and PNG attachments are allowed.")
                content = base64.b64decode(str(attachment.get("data_base64") or ""), validate=True)
                if not content or len(content) > 5 * 1024 * 1024:
                    raise ValidationError("The attachment must be smaller than 5 MB.")
                attachment_values = {
                    "name": name or "supporting-document",
                    "datas": base64.b64encode(content),
                    "mimetype": mimetype,
                }
            leave = Leave.with_context(employee_id=employee.id).create({
                "employee_id": employee.id,
                "holiday_status_id": leave_type.id,
                "request_date_from": start,
                "request_date_to": end,
                "notes": reason,
            })
            if attachment_values:
                request.env["ir.attachment"].sudo().create({
                    **attachment_values,
                    "res_model": "hr.leave",
                    "res_id": leave.id,
                })
            manager = employee.parent_id
            if manager and "alezdhar.mobile.notification.inbox" in request.env:
                request.env["alezdhar.mobile.notification.inbox"].notify_employee(
                    manager,
                    "طلب إجازة جديد",
                    f"أرسل {employee.name} طلب إجازة جديدًا.",
                    "leave_submitted",
                    title_en="New time-off request",
                    body_en=f"{employee.name} submitted a new time-off request.",
                )
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UserError, ValidationError) as exc:
            return AlezdharMobileApiV1._response(status="error", error={"code": "leave_validation_failed", "message": str(exc)}, code=422, request_id=request_id)
        return AlezdharMobileApiV1._response(data=self._leave_dto(leave), code=201, request_id=request_id)

    @http.route(API_PREFIX + "/leave/requests/team", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def team_leave_requests(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        rows = request.env["hr.leave"].sudo().search([
            ("employee_id.parent_id", "=", manager.id),
            ("employee_id", "!=", manager.id),
            ("employee_id.company_id", "=", manager.company_id.id),
            ("state", "=", "confirm"),
        ], limit=100, order="request_date_from, id")
        return AlezdharMobileApiV1._response(
            data={"items": [self._leave_dto(row) for row in rows]}, request_id=request_id
        )

    @http.route(API_PREFIX + "/leave/requests/<int:leave_id>/review", type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def review_leave_request(self, leave_id, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        leave = request.env["hr.leave"].sudo().search([
            ("id", "=", leave_id),
            ("employee_id.parent_id", "=", manager.id),
            ("employee_id", "!=", manager.id),
            ("employee_id.company_id", "=", manager.company_id.id),
        ], limit=1)
        if not leave:
            return AlezdharMobileApiV1._response(
                status="error", error={"code": "leave_not_found", "message": "Leave request not found."},
                code=404, request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            decision = str(payload.get("decision") or "").strip()
            note = str(payload.get("note") or "").strip()
            leave.mobile_review(manager, decision, note)
            if "alezdhar.mobile.notification.inbox" in request.env:
                approved = decision == "approve"
                request.env["alezdhar.mobile.notification.inbox"].notify_employee(
                    leave.employee_id,
                    "تم قبول طلب الإجازة" if approved else "تم رفض طلب الإجازة",
                    "تم اعتماد طلب إجازتك." if approved else f"سبب الرفض: {note}",
                    "leave_result",
                    title_en="Time-off request approved" if approved else "Time-off request rejected",
                    body_en="Your time-off request was approved." if approved else f"Rejection reason: {note}",
                )
        except (UserError, ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return AlezdharMobileApiV1._response(
                status="error", error={"code": "leave_review_failed", "message": str(exc)},
                code=422, request_id=request_id,
            )
        return AlezdharMobileApiV1._response(data=self._leave_dto(leave), request_id=request_id)
