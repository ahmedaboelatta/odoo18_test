import json
from datetime import date

from odoo import http
from odoo.exceptions import AccessDenied, ValidationError
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
        return {
            "id": leave.id,
            "type_id": leave.holiday_status_id.id,
            "type_name": leave.holiday_status_id.name,
            "date_from": leave.request_date_from.isoformat(),
            "date_to": leave.request_date_to.isoformat(),
            "days": leave.number_of_days,
            "reason": leave.notes or "",
            "state": leave.state,
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
        balances = [{"type_id": item.id, "name": item.name, "remaining_days": item.virtual_remaining_leaves,
                     "requires_allocation": item.requires_allocation != "no"} for item in types
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
            leave = Leave.with_context(employee_id=employee.id).create({
                "employee_id": employee.id,
                "holiday_status_id": leave_type.id,
                "request_date_from": start,
                "request_date_to": end,
                "notes": reason,
            })
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            return AlezdharMobileApiV1._response(status="error", error={"code": "leave_validation_failed", "message": str(exc)}, code=422, request_id=request_id)
        return AlezdharMobileApiV1._response(data=self._leave_dto(leave), code=201, request_id=request_id)
