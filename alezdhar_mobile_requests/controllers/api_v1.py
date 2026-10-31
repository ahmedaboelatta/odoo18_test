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
            "attachments": [{
                "id": item.id,
                "name": item.name,
                "mimetype": item.mimetype,
                "size": item.file_size,
            } for item in attachments],
        }

    @staticmethod
    def _audit(session, event_type, request_id, metadata):
        request.env["alezdhar.mobile.audit"].sudo().create({
            "identity_id": session.identity_id.id,
            "company_id": session.identity_id.employee_id.company_id.id,
            "event_type": event_type,
            "request_id": request_id,
            "outcome": "success",
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
        })

    @staticmethod
    def _post_as_employee(leave, employee, body):
        partner = employee.work_contact_id
        leave.sudo().message_post(
            body=body,
            author_id=partner.id if partner else None,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

    @http.route(API_PREFIX + "/leave/summary", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def summary(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        LeaveType = request.env["hr.leave.type"].sudo().with_context(employee_id=employee.id)
        types = LeaveType.search([("active", "=", True), ("company_id", "in", [False, employee.company_id.id])])
        balances = []
        for item in types:
            taken = item.leaves_taken
            allocated = item.max_leaves
            remaining = item.virtual_remaining_leaves
            has_history = request.env["hr.leave"].sudo().search_count([
                ("employee_id", "=", employee.id),
                ("holiday_status_id", "=", item.id),
                ("state", "not in", ["cancel"]),
            ])
            if not any(abs(value or 0) > 0.0001 for value in (taken, allocated, remaining)) and not has_history:
                continue
            balances.append({
                "type_id": item.id,
                "name": item.name,
                "allocated_days": allocated,
                "taken_days": taken,
                "remaining_days": remaining,
                "requires_allocation": item.requires_allocation != "no",
            })
        pending = request.env["hr.leave"].sudo().search_count([
            ("employee_id", "=", employee.id), ("state", "in", ["confirm", "validate1"])
        ])
        return AlezdharMobileApiV1._response(data={"balances": balances, "pending_count": pending}, request_id=request_id)

    @http.route(API_PREFIX + "/schedule/week", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def week_schedule(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        calendar = employee.resource_calendar_id
        rows = calendar.attendance_ids.filtered(
            lambda row: not row.display_type and row.day_period != "lunch"
        ).sorted(lambda row: (int(row.dayofweek), row.hour_from))
        items = [{
            "day_of_week": int(row.dayofweek),
            "hour_from": row.hour_from,
            "hour_to": row.hour_to,
            "name": row.name or "",
        } for row in rows]
        return AlezdharMobileApiV1._response(data={
            "calendar_name": calendar.name or "",
            "timezone": calendar.tz or "UTC",
            "items": items,
        }, request_id=request_id)

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
            self._post_as_employee(
                leave, employee,
                f"Mobile request submitted by {employee.name}.",
            )
            self._audit(session, "leave_request_submitted", request_id, {
                "employee_id": employee.id,
                "employee_name": employee.name,
                "leave_id": leave.id,
                "days": leave.number_of_days,
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

    @http.route(API_PREFIX + "/leave/attachments/<int:attachment_id>", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def leave_attachment(self, attachment_id, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        attachment = request.env["ir.attachment"].sudo().search([
            ("id", "=", attachment_id), ("res_model", "=", "hr.leave")
        ], limit=1)
        leave = request.env["hr.leave"].sudo().browse(attachment.res_id).exists() if attachment else request.env["hr.leave"]
        if not leave or (leave.employee_id != employee and leave.employee_id.parent_id != employee):
            return AlezdharMobileApiV1._response(
                status="error", error={"code": "attachment_not_found", "message": "Attachment not found."},
                code=404, request_id=request_id,
            )
        self._audit(session, "leave_attachment_downloaded", request_id, {
            "employee_id": employee.id,
            "employee_name": employee.name,
            "leave_id": leave.id,
            "attachment_id": attachment.id,
        })
        return request.make_response(
            base64.b64decode(attachment.datas or b""),
            headers=[
                ("Content-Type", attachment.mimetype or "application/octet-stream"),
                ("Content-Disposition", f'attachment; filename="{attachment.name}"'),
            ],
        )

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
            self._post_as_employee(
                leave, manager,
                f"Mobile request {'approved' if decision == 'approve' else 'rejected'} by {manager.name}."
                + (f" Note: {note}" if note else ""),
            )
            self._audit(session, "leave_request_reviewed", request_id, {
                "manager_id": manager.id,
                "manager_name": manager.name,
                "employee_id": leave.employee_id.id,
                "employee_name": leave.employee_id.name,
                "leave_id": leave.id,
                "decision": decision,
            })
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

    @http.route(API_PREFIX + "/services", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def services(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        Lang = request.env["res.lang"].sudo()
        preferred = "en_US" if locale == "en" else "ar_001"
        lang = preferred if Lang.search_count([("code", "=", preferred), ("active", "=", True)]) else request.env.lang
        rows = request.env["alezdhar.mobile.service"].sudo().with_context(lang=lang).search([
            ("active", "=", True), ("state", "=", "published"),
            ("company_id", "in", [False, employee.company_id.id])
        ])
        return AlezdharMobileApiV1._response(data={"items": [{
            "id": row.id, "name": row.name, "description": row.description or "",
            "icon": row.icon, "allow_attachment": row.allow_attachment,
            "service_type": row.service_type,
            "fields": [{
                "key": field.key, "label": field.label, "type": field.field_type,
                "required": field.required,
                "options": [{"label": option.label, "value": option.value} for option in field.option_ids],
            } for field in row.field_ids],
        } for row in rows]}, request_id=request_id)

    @staticmethod
    def _service_request_dto(row):
        attachments = request.env["ir.attachment"].sudo().search([
            ("res_model", "=", "alezdhar.mobile.service.request"), ("res_id", "=", row.id)
        ])
        return {
            "id": row.id, "reference": row.name, "service_id": row.service_id.id,
            "service_name": row.service_id.name, "description": row.description,
            "state": row.state, "resolution": row.resolution or "",
            "service_type": row.service_id.service_type,
            "created_at": row.create_date.isoformat() if row.create_date else None,
            "attachments": [{"id": item.id, "name": item.name, "mimetype": item.mimetype}
                            for item in attachments],
        }

    @http.route(API_PREFIX + "/service-requests", type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def service_requests(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        Request = request.env["alezdhar.mobile.service.request"].sudo()
        if request.httprequest.method == "GET":
            rows = Request.search([("employee_id", "=", employee.id)], limit=100)
            return AlezdharMobileApiV1._response(
                data={"items": [self._service_request_dto(row) for row in rows]}, request_id=request_id
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            description = str(payload.get("description") or "").strip()
            answers = payload.get("answers") or {}
            service = request.env["alezdhar.mobile.service"].sudo().search([
                ("id", "=", int(payload.get("service_id"))), ("active", "=", True),
                ("state", "=", "published"),
                ("company_id", "in", [False, employee.company_id.id]),
            ], limit=1)
            if not service or len(description) < 5:
                raise ValidationError("A valid service and description are required.")
            allowed_keys = set(service.field_ids.mapped("key"))
            if not isinstance(answers, dict) or set(answers) - allowed_keys:
                raise ValidationError("Invalid service request answers.")
            for field in service.field_ids:
                value = str(answers.get(field.key) or "").strip()
                if field.required and not value:
                    raise ValidationError(f"{field.label} is required.")
                if field.field_type in ("radio", "select") and value and value not in field.option_ids.mapped("value"):
                    raise ValidationError(f"Invalid value for {field.label}.")
            row = Request.create({
                "service_id": service.id, "employee_id": employee.id,
                "description": description, "answers_json": answers,
            })
            attachment = payload.get("attachment")
            if attachment and service.allow_attachment:
                mimetype = str(attachment.get("mimetype") or "application/octet-stream")[:128]
                if mimetype not in {"application/pdf", "image/jpeg", "image/png"}:
                    raise ValidationError("Only PDF, JPG and PNG attachments are allowed.")
                content = base64.b64decode(str(attachment.get("data_base64") or ""), validate=True)
                if not content or len(content) > 5 * 1024 * 1024:
                    raise ValidationError("The attachment must be smaller than 5 MB.")
                request.env["ir.attachment"].sudo().create({
                    "name": str(attachment.get("name") or "attachment")[:255],
                    "datas": base64.b64encode(content), "mimetype": mimetype,
                    "res_model": row._name, "res_id": row.id,
                })
            partner = employee.work_contact_id
            row.message_post(
                body=f"Mobile service request submitted by {employee.name}.",
                author_id=partner.id if partner else None,
                message_type="comment", subtype_xmlid="mail.mt_note",
            )
            self._audit(session, "service_request_submitted", request_id, {
                "employee_id": employee.id, "employee_name": employee.name,
                "service_request_id": row.id, "service": service.code,
            })
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, ValidationError) as exc:
            return AlezdharMobileApiV1._response(
                status="error", error={"code": "service_request_validation_failed", "message": str(exc)},
                code=422, request_id=request_id,
            )
        return AlezdharMobileApiV1._response(data=self._service_request_dto(row), code=201, request_id=request_id)
