import base64
import binascii
import json
import re
from datetime import date, datetime, timedelta

from odoo import fields, http
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.http import request

from odoo.addons.hader_mobile_core.controllers.api_v1 import (
    API_PREFIX,
    HaderMobileApiV1,
    api_routes,
)


class HaderLeaveApiV1(http.Controller):
    @staticmethod
    def _session(request_id):
        try:
            return HaderMobileApiV1._authenticated_session(), None
        except AccessDenied:
            return None, HaderMobileApiV1._response(
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
        request.env["hader.mobile.audit"].sudo().create({
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

    @http.route(api_routes("/leave/summary"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def summary(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
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
        return HaderMobileApiV1._response(data={"balances": balances, "pending_count": pending}, request_id=request_id)

    @http.route(api_routes("/schedule/week"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def week_schedule(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
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
        return HaderMobileApiV1._response(data={
            "calendar_name": calendar.name or "",
            "timezone": calendar.tz or "UTC",
            "items": items,
        }, request_id=request_id)

    @http.route(api_routes("/leave/requests"), type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def leave_requests(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        Leave = request.env["hr.leave"].sudo()
        if request.httprequest.method == "GET":
            rows = Leave.search([("employee_id", "=", employee.id)], limit=50, order="request_date_from desc, id desc")
            return HaderMobileApiV1._response(data={"items": [self._leave_dto(row) for row in rows]}, request_id=request_id)
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
            manager = (
                employee._get_mobile_approver_employee("leave_manager_id")
                if hasattr(employee, "_get_mobile_approver_employee")
                else employee.parent_id
            )
            if manager and "hader.mobile.notification.inbox" in request.env:
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    manager,
                    "طلب إجازة جديد",
                    f"أرسل {employee.name} طلب إجازة جديدًا ({leave_type.name}).",
                    "leave_submitted",
                    title_en="New time-off request",
                    body_en=f"{employee.name} submitted a new time-off request ({leave_type.name}).",
                )
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(status="error", error={"code": "leave_validation_failed", "message": str(exc)}, code=422, request_id=request_id)
        return HaderMobileApiV1._response(data=self._leave_dto(leave), code=201, request_id=request_id)

    @http.route(api_routes("/leave/attachments/<int:attachment_id>"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def leave_attachment(self, attachment_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        attachment = request.env["ir.attachment"].sudo().search([
            ("id", "=", attachment_id), ("res_model", "=", "hr.leave")
        ], limit=1)
        leave = request.env["hr.leave"].sudo().browse(attachment.res_id).exists() if attachment else request.env["hr.leave"]
        can_access = bool(
            leave and (
                leave.employee_id == employee
                or (
                    hasattr(leave.employee_id, "_is_mobile_approver")
                    and leave.employee_id._is_mobile_approver(employee, "leave_manager_id")
                )
                or leave.employee_id.parent_id == employee
            )
        )
        if not can_access:
            return HaderMobileApiV1._response(
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

    @http.route(api_routes("/leave/requests/team"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def team_leave_requests(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        emp_domain = (
            manager._mobile_team_domain("leave_manager_id")
            if hasattr(manager, "_mobile_team_domain")
            else [("parent_id", "=", manager.id), ("id", "!=", manager.id)]
        )
        team_emp_ids = request.env["hr.employee"].sudo().search(
            emp_domain + [("company_id", "=", manager.company_id.id)]
        ).ids
        rows = request.env["hr.leave"].sudo().search([
            ("employee_id", "in", team_emp_ids),
            ("state", "=", "confirm"),
        ], limit=100, order="request_date_from, id")
        return HaderMobileApiV1._response(
            data={"items": [self._leave_dto(row) for row in rows]}, request_id=request_id
        )

    @http.route(api_routes("/leave/requests/<int:leave_id>/review"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def review_leave_request(self, leave_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        leave = request.env["hr.leave"].sudo().browse(leave_id).exists()
        is_allowed = bool(
            leave
            and leave.employee_id.company_id == manager.company_id
            and (
                (
                    hasattr(leave.employee_id, "_is_mobile_approver")
                    and leave.employee_id._is_mobile_approver(manager, "leave_manager_id")
                )
                or (leave.employee_id.parent_id == manager and leave.employee_id != manager)
            )
        )
        if not is_allowed:
            return HaderMobileApiV1._response(
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
            if "hader.mobile.notification.inbox" in request.env:
                approved = decision == "approve"
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    leave.employee_id,
                    "تم قبول طلب الإجازة" if approved else "تم رفض طلب الإجازة",
                    "تم اعتماد طلب إجازتك." if approved else f"سبب الرفض: {note}",
                    "leave_result",
                    title_en="Time-off request approved" if approved else "Time-off request rejected",
                    body_en="Your time-off request was approved." if approved else f"Rejection reason: {note}",
                )
        except (UserError, ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return HaderMobileApiV1._response(
                status="error", error={"code": "leave_review_failed", "message": str(exc)},
                code=422, request_id=request_id,
            )
        return HaderMobileApiV1._response(data=self._leave_dto(leave), request_id=request_id)

    @http.route(api_routes("/services"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def services(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        Lang = request.env["res.lang"].sudo()
        preferred = "en_US" if locale == "en" else "ar_001"
        lang = preferred if Lang.search_count([("code", "=", preferred), ("active", "=", True)]) else request.env.lang
        rows = request.env["hader.mobile.service"].sudo().with_context(lang=lang).search([
            ("active", "=", True), ("state", "=", "published"),
            ("company_id", "in", [False, employee.company_id.id])
        ])
        return HaderMobileApiV1._response(data={"items": [{
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
            ("res_model", "=", "hader.mobile.service.request"), ("res_id", "=", row.id)
        ])
        return {
            "id": row.id, "reference": row.name, "service_id": row.service_id.id,
            "service_name": row.service_id.name, "description": row.description,
            "state": row.state, "resolution": row.resolution or "",
            "service_type": row.service_id.service_type,
            "employee_name": row.employee_id.name or "",
            "answers": row.answers_json or {},
            "created_at": row.create_date.isoformat() if row.create_date else None,
            "attachments": [{"id": item.id, "name": item.name, "mimetype": item.mimetype, "size": item.file_size}
                            for item in attachments],
        }

    @http.route(api_routes("/service-requests"), type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def service_requests(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        Request = request.env["hader.mobile.service.request"].sudo()
        if request.httprequest.method == "GET":
            rows = Request.search([("employee_id", "=", employee.id)], limit=100)
            return HaderMobileApiV1._response(
                data={"items": [self._service_request_dto(row) for row in rows]}, request_id=request_id
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            description = str(payload.get("description") or "").strip()
            answers = payload.get("answers") or {}
            service = request.env["hader.mobile.service"].sudo().search([
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
            manager = employee.parent_id
            if manager and "hader.mobile.notification.inbox" in request.env:
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    manager,
                    "طلب خدمة جديد",
                    f"أرسل {employee.name} طلب خدمة جديد ({row.name} - {service.name}).",
                    "service_submitted",
                    title_en="New service request",
                    body_en=f"{employee.name} submitted a new service request ({row.name} - {service.name}).",
                )
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error", error={"code": "service_request_validation_failed", "message": str(exc)},
                code=422, request_id=request_id,
            )
        return HaderMobileApiV1._response(data=self._service_request_dto(row), code=201, request_id=request_id)

    @http.route(api_routes("/service-requests/team"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def team_service_requests(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        domain = [
            ("employee_id", "!=", manager.id),
            ("company_id", "=", manager.company_id.id),
            ("state", "in", ["submitted", "in_progress"]),
        ]
        if manager.user_id:
            domain = [
                "&", "&",
                ("employee_id", "!=", manager.id),
                ("company_id", "=", manager.company_id.id),
                ("state", "in", ["submitted", "in_progress"]),
                "|", "|",
                ("employee_id.parent_id", "=", manager.id),
                ("assigned_user_id", "=", manager.user_id.id),
                ("assigned_user_ids", "in", [manager.user_id.id]),
            ]
        else:
            domain.append(("employee_id.parent_id", "=", manager.id))
        rows = request.env["hader.mobile.service.request"].sudo().search(
            domain, limit=100, order="create_date desc, id desc"
        )
        return HaderMobileApiV1._response(
            data={"items": [self._service_request_dto(row) for row in rows]},
            request_id=request_id,
        )

    @http.route(api_routes("/service-requests/<int:service_request_id>/review"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def review_service_request(self, service_request_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        row = request.env["hader.mobile.service.request"].sudo().browse(service_request_id).exists()
        is_direct_manager = bool(row and row.employee_id.parent_id == manager and row.employee_id != manager)
        is_assigned_user = bool(
            row and manager.user_id and (
                row.assigned_user_id == manager.user_id or manager.user_id in row.assigned_user_ids
            )
        )
        if not row or row.company_id != manager.company_id or not (is_direct_manager or is_assigned_user):
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "service_request_not_found", "message": "Service request not found."},
                code=404,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            decision = str(payload.get("decision") or "").strip()
            note = str(payload.get("note") or "").strip()
            row.mobile_review(manager, decision, note)
            self._post_as_employee(
                row,
                manager,
                f"Mobile service request {'approved' if decision == 'approve' else 'rejected'} by {manager.name}."
                + (f" Note: {note}" if note else ""),
            )
            self._audit(session, "service_request_reviewed", request_id, {
                "manager_id": manager.id,
                "manager_name": manager.name,
                "employee_id": row.employee_id.id,
                "employee_name": row.employee_id.name,
                "service_request_id": row.id,
                "decision": decision,
            })
            if "hader.mobile.notification.inbox" in request.env:
                approved = decision == "approve"
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    row.employee_id,
                    "تم اعتماد طلب الخدمة" if approved else "تم رفض طلب الخدمة",
                    f"تم اعتماد طلبك ({row.service_id.name} - {row.name})."
                    if approved
                    else f"تم رفض طلبك ({row.service_id.name} - {row.name}). السبب: {note}",
                    "service_result",
                    title_en="Service request approved" if approved else "Service request rejected",
                    body_en=f"Your request ({row.service_id.name} - {row.name}) was approved."
                    if approved
                    else f"Your request ({row.service_id.name} - {row.name}) was rejected. Reason: {note}",
                )
        except (UserError, ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "service_request_review_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(data=self._service_request_dto(row), request_id=request_id)

    @staticmethod
    def _expense_dto(expense, locale="ar"):
        attachments = request.env["ir.attachment"].sudo().search([
            ("res_model", "=", "hader.mobile.expense"),
            ("res_id", "=", expense.id),
        ])
        cat_label = expense.category_id.label_for_locale(locale) if expense.category_id else ""
        return {
            "id": expense.id,
            "reference": expense.name or "",
            "category_id": expense.category_id.id,
            "category_name": cat_label,
            "title": expense.title or "",
            "expense_date": expense.expense_date.isoformat() if expense.expense_date else None,
            "amount": float(expense.amount or 0.0),
            "currency": expense.currency_id.symbol or expense.currency_id.name or "SAR",
            "notes": expense.notes or "",
            "state": expense.state,
            "employee_name": expense.employee_id.name or "",
            "manager_review_note": expense.manager_review_note or "",
            "admin_note": expense.admin_note or "",
            "created_at": expense.create_date.isoformat() if expense.create_date else None,
            "attachments": [
                {
                    "id": item.id,
                    "name": item.name,
                    "mimetype": item.mimetype,
                    "size": item.file_size,
                }
                for item in attachments
            ],
        }

    @http.route(api_routes("/expenses/categories"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def expense_categories(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        rows = request.env["hader.mobile.expense.category"].sudo().search([
            ("active", "=", True),
            ("company_id", "in", [False, employee.company_id.id]),
        ])
        return HaderMobileApiV1._response(
            data={
                "items": [
                    {
                        "id": row.id,
                        "code": row.code,
                        "name": row.label_for_locale(locale),
                        "name_ar": row.name_ar,
                        "name_en": row.name_en,
                    }
                    for row in rows
                ]
            },
            request_id=request_id,
        )

    @http.route(api_routes("/expenses"), type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def expenses(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        Expense = request.env["hader.mobile.expense"].sudo()
        if request.httprequest.method == "GET":
            rows = Expense.search(
                [("employee_id", "=", employee.id), ("active", "=", True)],
                limit=100,
                order="expense_date desc, id desc",
            )
            approved_total = sum(r.amount for r in rows if r.state == "approved")
            pending_total = sum(r.amount for r in rows if r.state in ("submitted", "manager_approved"))
            pending_count = sum(1 for r in rows if r.state in ("submitted", "manager_approved"))
            currency = employee.company_id.currency_id.symbol or employee.company_id.currency_id.name or "SAR"
            return HaderMobileApiV1._response(
                data={
                    "summary": {
                        "approved_total": round(approved_total, 2),
                        "pending_total": round(pending_total, 2),
                        "pending_count": pending_count,
                        "currency": currency,
                    },
                    "items": [self._expense_dto(row, locale) for row in rows],
                },
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            title = str(payload.get("title") or "").strip()
            notes = str(payload.get("notes") or "").strip()
            amount = float(payload.get("amount") or 0.0)
            exp_date_str = str(payload.get("expense_date") or "").strip()
            exp_date = date.fromisoformat(exp_date_str) if exp_date_str else date.today()
            category = request.env["hader.mobile.expense.category"].sudo().search([
                ("id", "=", int(payload.get("category_id") or 0)),
                ("active", "=", True),
                ("company_id", "in", [False, employee.company_id.id]),
            ], limit=1)
            if not category or not title or amount <= 0:
                raise ValidationError("بيان المصروف والتصنيف والمبلغ الصحيح مطلوبة. / Valid category, title, and positive amount are required.")

            raw_attachments = payload.get("attachments") or []
            if payload.get("attachment") and isinstance(payload.get("attachment"), dict):
                raw_attachments = [payload.get("attachment")]
            validated_attachments = []
            for att in raw_attachments:
                if not isinstance(att, dict):
                    continue
                name = str(att.get("name") or "receipt").strip()[:255]
                mimetype = str(att.get("mimetype") or "application/octet-stream")[:128]
                if mimetype not in {"application/pdf", "image/jpeg", "image/png"}:
                    raise ValidationError("يسمح فقط بمرفقات PDF أو JPG أو PNG. / Only PDF, JPG and PNG attachments are allowed.")
                content = base64.b64decode(str(att.get("data_base64") or ""), validate=True)
                if not content or len(content) > 5 * 1024 * 1024:
                    raise ValidationError("حجم المرفق يجب ألا يتجاوز 5 ميجابايت. / Each attachment must be smaller than 5 MB.")
                validated_attachments.append({
                    "name": name or "expense-receipt",
                    "datas": base64.b64encode(content),
                    "mimetype": mimetype,
                })

            expense = Expense.create({
                "employee_id": employee.id,
                "category_id": category.id,
                "title": title,
                "expense_date": exp_date,
                "amount": amount,
                "notes": notes,
            })
            created_att_ids = []
            for att_vals in validated_attachments:
                att_rec = request.env["ir.attachment"].sudo().create({
                    **att_vals,
                    "res_model": "hader.mobile.expense",
                    "res_id": expense.id,
                })
                created_att_ids.append(att_rec.id)

            partner = employee.work_contact_id
            expense.sudo().message_post(
                body=f"تم تقديم طلب مصروف من تطبيق حاضر بواسطة {employee.name} بمبلغ {amount:.2f}.",
                author_id=partner.id if partner else None,
                attachment_ids=created_att_ids,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
            self._audit(session, "expense_request_submitted", request_id, {
                "employee_id": employee.id,
                "employee_name": employee.name,
                "expense_id": expense.id,
                "amount": amount,
                "attachments_count": len(created_att_ids),
            })
            manager = (
                expense.manager_id
                or (
                    employee._get_mobile_approver_employee("expense_manager_id")
                    if hasattr(employee, "_get_mobile_approver_employee")
                    else employee.parent_id
                )
            )
            if manager and "hader.mobile.notification.inbox" in request.env:
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    manager,
                    "طلب مصاريف جديد",
                    f"أرسل {employee.name} طلب صرف مصاريف ({expense.name} - {title}) بمبلغ {amount:.2f}.",
                    "expense_submitted",
                    title_en="New expense request",
                    body_en=f"{employee.name} submitted a new expense request ({expense.name} - {title}) for {amount:.2f}.",
                )
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "expense_validation_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(data=self._expense_dto(expense, locale), code=201, request_id=request_id)

    @http.route(api_routes("/expenses/attachments/<int:attachment_id>"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def expense_attachment(self, attachment_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        attachment = request.env["ir.attachment"].sudo().search([
            ("id", "=", attachment_id),
            ("res_model", "=", "hader.mobile.expense"),
        ], limit=1)
        expense = request.env["hader.mobile.expense"].sudo().browse(attachment.res_id).exists() if attachment else request.env["hader.mobile.expense"]
        can_access = bool(
            expense and (
                expense.employee_id == employee
                or expense.manager_id == employee
                or (
                    hasattr(expense.employee_id, "_is_mobile_approver")
                    and expense.employee_id._is_mobile_approver(employee, "expense_manager_id")
                )
                or expense.employee_id.parent_id == employee
            )
        )
        if not can_access:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "attachment_not_found", "message": "Attachment not found."},
                code=404,
                request_id=request_id,
            )
        return request.make_response(
            base64.b64decode(attachment.datas or b""),
            headers=[
                ("Content-Type", attachment.mimetype or "application/octet-stream"),
                ("Content-Disposition", f'attachment; filename="{attachment.name}"'),
            ],
        )

    @http.route(api_routes("/expenses/team"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def team_expenses(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        emp_domain = (
            manager._mobile_team_domain("expense_manager_id")
            if hasattr(manager, "_mobile_team_domain")
            else [("parent_id", "=", manager.id), ("id", "!=", manager.id)]
        )
        team_emp_ids = request.env["hr.employee"].sudo().search(
            emp_domain + [("company_id", "=", manager.company_id.id)]
        ).ids
        rows = request.env["hader.mobile.expense"].sudo().search([
            "|",
            ("employee_id", "in", team_emp_ids),
            ("manager_id", "=", manager.id),
            ("employee_id", "!=", manager.id),
            ("company_id", "=", manager.company_id.id),
            ("state", "=", "submitted"),
            ("active", "=", True),
        ], limit=100, order="create_date desc, id desc")
        return HaderMobileApiV1._response(
            data={"items": [self._expense_dto(row, locale) for row in rows]},
            request_id=request_id,
        )

    @http.route(api_routes("/expenses/<int:expense_id>/review"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def review_expense(self, expense_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        expense = request.env["hader.mobile.expense"].sudo().browse(expense_id).exists()
        is_allowed = bool(
            expense
            and expense.active
            and expense.company_id == manager.company_id
            and expense.employee_id != manager
            and (
                expense.manager_id == manager
                or (
                    hasattr(expense.employee_id, "_is_mobile_approver")
                    and expense.employee_id._is_mobile_approver(manager, "expense_manager_id")
                )
                or expense.employee_id.parent_id == manager
            )
        )
        if not is_allowed:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "expense_not_found", "message": "Expense request not found."},
                code=404,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            decision = str(payload.get("decision") or "").strip()
            note = str(payload.get("note") or "").strip()
            expense.mobile_review(manager, decision, note)
            self._post_as_employee(
                expense,
                manager,
                f"تمت مراجعة طلب المصروف من تطبيق حاضر بواسطة المدير المباشر {manager.name}: "
                f"{'موافقة واعتماد مبدئي' if decision == 'approve' else 'رفض'}."
                + (f" ملاحظة: {note}" if note else ""),
            )
            self._audit(session, "expense_request_reviewed", request_id, {
                "manager_id": manager.id,
                "manager_name": manager.name,
                "employee_id": expense.employee_id.id,
                "employee_name": expense.employee_id.name,
                "expense_id": expense.id,
                "decision": decision,
            })
            if "hader.mobile.notification.inbox" in request.env:
                approved = decision == "approve"
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    expense.employee_id,
                    "موافقة المدير على طلب المصاريف" if approved else "تم رفض طلب المصاريف من المدير",
                    f"وافق مديرك المباشر ({manager.name}) على طلب المصروف ({expense.name} - {expense.title}) وتم رفعه للإدارة."
                    if approved
                    else f"تم رفض طلب المصروف ({expense.name} - {expense.title}). السبب: {note}",
                    "expense_result",
                    title_en="Manager approved your expense" if approved else "Expense request rejected by manager",
                    body_en=f"Your manager ({manager.name}) approved your expense ({expense.name} - {expense.title}) and forwarded it to accounting."
                    if approved
                    else f"Your expense ({expense.name} - {expense.title}) was rejected. Reason: {note}",
                )
        except (UserError, ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "expense_review_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(data=self._expense_dto(expense, locale), request_id=request_id)

    # -------------------------------------------------------------------------
    # Employee Calendar & Meetings (calendar.event)
    # Accessible to ALL employees (with or without employee.user_id) via their
    # partner (user_id.partner_id or work_contact_id).
    # -------------------------------------------------------------------------

    @staticmethod
    def _ensure_employee_partner(employee):
        emp = employee.sudo()
        if emp.user_id and emp.user_id.partner_id:
            return emp.user_id.partner_id
        if emp.work_contact_id:
            return emp.work_contact_id
        partner = request.env["res.partner"].sudo().create({
            "name": emp.name or "Employee",
            "email": emp.work_email or False,
            "phone": emp.mobile_phone or emp.work_phone or False,
            "company_id": emp.company_id.id if emp.company_id else False,
        })
        emp.write({"work_contact_id": partner.id})
        return partner

    @classmethod
    def _calendar_context(cls, session, request_id):
        employee = session.identity_id.employee_id.sudo()
        if "calendar.event" not in request.env:
            locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
            msg = (
                "Calendar module is not enabled on this server."
                if locale == "en"
                else "موديول التقويم غير مفعل على السيرفر."
            )
            return None, None, None, HaderMobileApiV1._response(
                status="error",
                error={"code": "calendar_unavailable", "message": msg},
                code=403,
                request_id=request_id,
            )
        partner = cls._ensure_employee_partner(employee)
        user = employee.user_id
        return employee, user, partner, None

    @staticmethod
    def _clean_html(raw):
        text = str(raw or "")
        if not text:
            return ""
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()

    @classmethod
    def _calendar_event_dto(cls, event, user, partner):
        attendees = []
        for att in event.attendee_ids:
            attendees.append({
                "partner_id": att.partner_id.id,
                "name": att.common_name or att.partner_id.name or "",
                "state": att.state or "accepted",
            })
        if not attendees and event.partner_ids:
            for p in event.partner_ids:
                attendees.append({
                    "partner_id": p.id,
                    "name": p.name or "",
                    "state": "accepted",
                })
        is_org = bool(
            (user and event.user_id == user)
            or (partner and event.partner_ids and event.partner_ids[:1] == partner)
        )
        return {
            "id": event.id,
            "title": event.name or "",
            "start": event.start.isoformat() if event.start else "",
            "stop": event.stop.isoformat() if event.stop else "",
            "allday": bool(event.allday),
            "location": event.location or "",
            "description": cls._clean_html(event.description),
            "organizer_name": event.user_id.name or "",
            "is_organizer": is_org,
            "attendees": attendees,
        }

    @staticmethod
    def _parse_event_dt(raw, allday=False, is_stop=False):
        value = str(raw or "").strip()
        if not value:
            raise ValidationError("Start and end time are required.")
        if allday and len(value) == 10:
            d = date.fromisoformat(value)
            return datetime(d.year, d.month, d.day, 23 if is_stop else 0, 59 if is_stop else 0, 0)
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.now().astimezone().tzinfo).replace(tzinfo=None)
        return dt

    @http.route(api_routes("/calendar/events"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def calendar_events(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee, user, partner, guard_err = self._calendar_context(session, request_id)
        if guard_err:
            return guard_err
        partner_id = partner.id
        cutoff = fields.Datetime.now() - timedelta(days=30)
        if user:
            domain = [
                "|",
                ("user_id", "=", user.id),
                ("partner_ids", "in", [partner_id]),
                ("stop", ">=", cutoff),
            ]
        else:
            domain = [
                ("partner_ids", "in", [partner_id]),
                ("stop", ">=", cutoff),
            ]
        events = request.env["calendar.event"].sudo().search(
            domain, limit=100, order="start asc, id asc"
        )
        colleagues_rows = request.env["hr.employee"].sudo().search([
            ("company_id", "=", employee.company_id.id),
            ("id", "!=", employee.id),
            ("active", "=", True),
        ], limit=500, order="name asc")
        colleagues = []
        seen_partners = {partner_id}
        for emp in colleagues_rows:
            p = cls_partner = self._ensure_employee_partner(emp)
            if p and p.id not in seen_partners:
                seen_partners.add(p.id)
                colleagues.append({
                    "partner_id": p.id,
                    "name": emp.name,
                    "job_title": emp.job_title or (emp.job_id.name if emp.job_id else ""),
                })
        return HaderMobileApiV1._response(
            data={
                "items": [self._calendar_event_dto(ev, user, partner) for ev in events],
                "colleagues": colleagues,
            },
            request_id=request_id,
        )

    @http.route(api_routes("/calendar/events"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def create_calendar_event(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee, user, partner, guard_err = self._calendar_context(session, request_id)
        if guard_err:
            return guard_err
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            title = str(payload.get("title") or "").strip()
            if not title:
                raise ValidationError("يرجى إدخال عنوان الموعد / الاجتماع.")
            allday = bool(payload.get("allday"))
            start_dt = self._parse_event_dt(payload.get("start"), allday=allday, is_stop=False)
            stop_dt = self._parse_event_dt(payload.get("stop") or payload.get("start"), allday=allday, is_stop=True)
            if stop_dt <= start_dt:
                stop_dt = start_dt + timedelta(hours=1)
            location = str(payload.get("location") or "").strip()
            description = str(payload.get("description") or "").strip()
            raw_partners = payload.get("partner_ids") or []
            partner_ids = {partner.id}
            if isinstance(raw_partners, list):
                for pid in raw_partners:
                    try:
                        partner_ids.add(int(pid))
                    except (ValueError, TypeError):
                        pass
            vals = {
                "name": title,
                "start": fields.Datetime.to_string(start_dt),
                "stop": fields.Datetime.to_string(stop_dt),
                "allday": allday,
                "location": location,
                "description": description,
                "partner_ids": [(6, 0, list(partner_ids))],
            }
            if user:
                vals["user_id"] = user.id
            if allday:
                vals["start_date"] = start_dt.date().isoformat()
                vals["stop_date"] = stop_dt.date().isoformat()
            CalEnv = request.env["calendar.event"].with_user(user).sudo() if user else request.env["calendar.event"].sudo()
            event = CalEnv.create(vals)
            self._audit(session, "calendar_event_created", request_id, {
                "employee_id": employee.id,
                "partner_id": partner.id,
                "event_id": event.id,
                "title": title,
            })
        except (ValueError, TypeError, json.JSONDecodeError, UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "calendar_validation_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(
            data=self._calendar_event_dto(event, user, partner),
            code=201,
            request_id=request_id,
        )

    @http.route(api_routes("/calendar/events/<int:event_id>/update"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def update_calendar_event(self, event_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee, user, partner, guard_err = self._calendar_context(session, request_id)
        if guard_err:
            return guard_err
        search_domain = [("id", "=", event_id)]
        if user:
            search_domain += ["|", ("user_id", "=", user.id), ("partner_ids", "in", [partner.id])]
        else:
            search_domain += [("partner_ids", "in", [partner.id])]
        event = request.env["calendar.event"].sudo().search(search_domain, limit=1)
        if not event:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "event_not_found", "message": "Event not found."},
                code=404,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            title = str(payload.get("title") or event.name or "").strip()
            if not title:
                raise ValidationError("يرجى إدخال عنوان الموعد / الاجتماع.")
            allday = bool(payload.get("allday", event.allday))
            start_dt = (
                self._parse_event_dt(payload.get("start"), allday=allday, is_stop=False)
                if payload.get("start")
                else event.start
            )
            stop_dt = (
                self._parse_event_dt(payload.get("stop"), allday=allday, is_stop=True)
                if payload.get("stop")
                else event.stop
            )
            if stop_dt <= start_dt:
                stop_dt = start_dt + timedelta(hours=1)
            vals = {
                "name": title,
                "start": fields.Datetime.to_string(start_dt),
                "stop": fields.Datetime.to_string(stop_dt),
                "allday": allday,
                "location": str(payload.get("location", event.location or "")).strip(),
                "description": str(payload.get("description", event.description or "")).strip(),
            }
            if "partner_ids" in payload and isinstance(payload.get("partner_ids"), list):
                partner_ids = {partner.id}
                for pid in payload.get("partner_ids"):
                    try:
                        partner_ids.add(int(pid))
                    except (ValueError, TypeError):
                        pass
                vals["partner_ids"] = [(6, 0, list(partner_ids))]
            if allday:
                vals["start_date"] = start_dt.date().isoformat()
                vals["stop_date"] = stop_dt.date().isoformat()
            target_ev = event.with_user(user).sudo() if user else event.sudo()
            target_ev.write(vals)
            self._audit(session, "calendar_event_updated", request_id, {
                "employee_id": employee.id,
                "partner_id": partner.id,
                "event_id": event.id,
                "title": title,
            })
        except (ValueError, TypeError, json.JSONDecodeError, UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "calendar_update_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(
            data=self._calendar_event_dto(event, user, partner),
            request_id=request_id,
        )

    @http.route(api_routes("/calendar/events/<int:event_id>/delete"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def delete_calendar_event(self, event_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee, user, partner, guard_err = self._calendar_context(session, request_id)
        if guard_err:
            return guard_err
        search_domain = [("id", "=", event_id)]
        if user:
            search_domain += ["|", ("user_id", "=", user.id), ("partner_ids", "in", [partner.id])]
        else:
            search_domain += [("partner_ids", "in", [partner.id])]
        event = request.env["calendar.event"].sudo().search(search_domain, limit=1)
        if not event:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "event_not_found", "message": "Event not found."},
                code=404,
                request_id=request_id,
            )
        try:
            target_ev = event.with_user(user).sudo() if user else event.sudo()
            if (user and event.user_id == user) or len(event.partner_ids) <= 1:
                target_ev.unlink()
            else:
                target_ev.write({
                    "partner_ids": [(3, partner.id)],
                })
            self._audit(session, "calendar_event_deleted", request_id, {
                "employee_id": employee.id,
                "partner_id": partner.id,
                "event_id": event_id,
            })
        except (UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "calendar_delete_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(
            data={"deleted": True, "id": event_id},
            request_id=request_id,
        )

    # =========================================================================
    # EMPLOYEE PERSONAL CUSTODY & ASSETS (عهدة الموظف الشخصية)
    # =========================================================================

    @http.route(api_routes("/custody"), type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def custody_items(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        Custody = request.env["hader.mobile.custody"].sudo()

        if request.httprequest.method == "GET":
            rows = Custody.search(
                [("employee_id", "=", employee.id), ("active", "=", True)],
                limit=100,
                order="create_date desc, id desc",
            )
            active_count = sum(1 for r in rows if r.state == "assigned")
            pending_count = sum(
                1 for r in rows if r.state in ("submitted", "manager_approved", "return_requested")
            )
            returned_count = sum(1 for r in rows if r.state == "returned")
            return HaderMobileApiV1._response(
                data={
                    "summary": {
                        "active_count": active_count,
                        "pending_count": pending_count,
                        "returned_count": returned_count,
                        "total_count": len(rows),
                    },
                    "items": [r.mobile_dto(locale) for r in rows],
                },
                request_id=request_id,
            )

        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            item_type = str(payload.get("item_type") or "laptop").strip()
            valid_types = {"laptop", "phone", "sim", "vehicle", "card", "tools", "other"}
            if item_type not in valid_types:
                item_type = "other"
            title = str(payload.get("title") or "").strip()
            if not title:
                raise ValidationError("يرجى إدخال اسم أو موديل العهدة.")
            serial_number = str(payload.get("serial_number") or "").strip()
            notes = str(payload.get("notes") or "").strip()
            req_date_str = str(payload.get("request_date") or "").strip()
            req_date = (
                fields.Date.from_string(req_date_str[:10])
                if req_date_str
                else fields.Date.context_today(Custody)
            )
            row = Custody.create({
                "employee_id": employee.id,
                "item_type": item_type,
                "title": title,
                "serial_number": serial_number,
                "request_date": req_date,
                "notes": notes,
                "state": "submitted",
            })

            attachments = payload.get("attachments") or []
            if payload.get("attachment") and not attachments:
                attachments = [payload.get("attachment")]
            att_ids = []
            for att_payload in attachments[:5]:
                if not isinstance(att_payload, dict):
                    continue
                mimetype = str(att_payload.get("mimetype") or "application/octet-stream")[:128]
                if mimetype not in {"application/pdf", "image/jpeg", "image/png"}:
                    raise ValidationError("Only PDF, JPG and PNG attachments are allowed.")
                content = base64.b64decode(str(att_payload.get("data_base64") or ""), validate=True)
                if not content or len(content) > 8 * 1024 * 1024:
                    raise ValidationError("Each attachment must be smaller than 8 MB.")
                att = request.env["ir.attachment"].sudo().create({
                    "name": str(att_payload.get("name") or "custody_photo")[:255],
                    "datas": base64.b64encode(content),
                    "mimetype": mimetype,
                    "res_model": "hader.mobile.custody",
                    "res_id": row.id,
                })
                att_ids.append(att.id)
            if att_ids:
                row.write({"attachment_ids": [(6, 0, att_ids)]})

            self._post_as_employee(
                row,
                employee,
                f"Mobile custody request ({row.title}) submitted by {employee.name}.",
            )
            self._audit(session, "custody_request_submitted", request_id, {
                "employee_id": employee.id,
                "custody_id": row.id,
                "reference": row.name,
                "title": row.title,
            })
            manager = row._get_approver_employee()
            if manager and "hader.mobile.notification.inbox" in request.env:
                request.env["hader.mobile.notification.inbox"].sudo().notify_employee(
                    manager,
                    "طلب عهدة شخصية جديد",
                    f"أرسل {employee.name} طلب عهدة ({row.title}) برقم {row.name}.",
                    "custody_submitted",
                    title_en="New custody request",
                    body_en=f"{employee.name} submitted a custody request ({row.title}) {row.name}.",
                )
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "custody_validation_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(
            data=row.mobile_dto(locale),
            code=201,
            request_id=request_id,
        )

    @http.route(api_routes("/custody/<int:custody_id>/return"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def request_custody_return(self, custody_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        row = request.env["hader.mobile.custody"].sudo().browse(custody_id).exists()
        if not row or row.employee_id.id != employee.id:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "custody_not_found", "message": "Custody item not found."},
                code=404,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            note = str(payload.get("note") or "").strip()
            row.mobile_request_return(employee, note)
        except (ValueError, TypeError, json.JSONDecodeError, UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "custody_return_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(data=row.mobile_dto(locale), request_id=request_id)

    @http.route(api_routes("/custody/team"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def team_custody(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        emp_domain = (
            manager._mobile_team_domain("expense_manager_id")
            if hasattr(manager, "_mobile_team_domain")
            else [("parent_id", "=", manager.id), ("id", "!=", manager.id)]
        )
        team_emp_ids = request.env["hr.employee"].sudo().search(
            emp_domain + [("company_id", "=", manager.company_id.id)]
        ).ids
        rows = request.env["hader.mobile.custody"].sudo().search([
            ("employee_id", "in", team_emp_ids),
            ("company_id", "=", manager.company_id.id),
            ("state", "in", ["submitted", "return_requested"]),
            ("active", "=", True),
        ], limit=100, order="create_date desc, id desc")
        return HaderMobileApiV1._response(
            data={"items": [r.mobile_dto(locale) for r in rows]},
            request_id=request_id,
        )

    @http.route(api_routes("/custody/<int:custody_id>/review"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def review_custody(self, custody_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        row = request.env["hader.mobile.custody"].sudo().browse(custody_id).exists()
        if not row or row.company_id != manager.company_id or not row._is_approver(manager):
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "custody_not_found", "message": "Custody request not found."},
                code=404,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            decision = str(payload.get("decision") or "").strip()
            note = str(payload.get("note") or "").strip()
            row.mobile_review(manager, decision, note)
            self._audit(session, "custody_reviewed", request_id, {
                "manager_id": manager.id,
                "custody_id": row.id,
                "decision": decision,
            })
        except (ValueError, TypeError, json.JSONDecodeError, UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "custody_review_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(data=row.mobile_dto(locale), request_id=request_id)

    @http.route(api_routes("/custody/attachments/<int:attachment_id>"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def custody_attachment(self, attachment_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        attachment = request.env["ir.attachment"].sudo().browse(attachment_id).exists()
        if not attachment or attachment.res_model != "hader.mobile.custody":
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "attachment_not_found", "message": "Attachment not found."},
                code=404,
                request_id=request_id,
            )
        row = request.env["hader.mobile.custody"].sudo().browse(attachment.res_id).exists()
        if not row or (row.employee_id != employee and not row._is_approver(employee)):
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "attachment_not_found", "message": "Attachment not found."},
                code=404,
                request_id=request_id,
            )
        content = base64.b64decode(attachment.datas or b"")
        return request.make_response(
            content,
            headers=[
                ("Content-Type", attachment.mimetype or "application/octet-stream"),
                ("Content-Disposition", f'inline; filename="{attachment.name}"'),
                ("X-Request-Id", request_id),
            ],
        )

    # =========================================================================
    # EMPLOYEE DAILY TASKS & ACTIVITIES (المهام والأنشطة اليومية)
    # =========================================================================

    @http.route(api_routes("/tasks"), type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def employee_tasks(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        Task = request.env["hader.mobile.task"].sudo()
        today = fields.Date.context_today(Task)

        emp_domain = (
            employee._mobile_team_domain()
            if hasattr(employee, "_mobile_team_domain")
            else [("parent_id", "=", employee.id), ("id", "!=", employee.id)]
        )
        team_employees = request.env["hr.employee"].sudo().search(
            emp_domain + [("company_id", "=", employee.company_id.id), ("active", "=", True)],
            order="name asc",
        )

        if request.httprequest.method == "GET":
            my_rows = Task.search(
                [("employee_id", "=", employee.id), ("active", "=", True)],
                limit=150,
            )
            team_rows = (
                Task.search(
                    [
                        "|",
                        ("employee_id", "in", team_employees.ids),
                        "&",
                        ("assigned_by_employee_id", "=", employee.id),
                        ("employee_id", "!=", employee.id),
                        ("active", "=", True),
                    ],
                    limit=150,
                )
                if team_employees
                else Task.browse()
            )
            todo_count = sum(1 for r in my_rows if r.state == "todo")
            in_progress_count = sum(1 for r in my_rows if r.state == "in_progress")
            done_count = sum(1 for r in my_rows if r.state == "done")
            overdue_count = sum(
                1
                for r in my_rows
                if r.due_date and r.due_date < today and r.state in ("todo", "in_progress")
            )
            return HaderMobileApiV1._response(
                data={
                    "summary": {
                        "todo_count": todo_count,
                        "in_progress_count": in_progress_count,
                        "done_count": done_count,
                        "overdue_count": overdue_count,
                        "total_count": len(my_rows),
                    },
                    "items": [r.mobile_dto() for r in my_rows],
                    "team_items": [r.mobile_dto() for r in team_rows],
                    "team_members": [
                        {
                            "id": emp.id,
                            "name": emp.name or "",
                            "job_title": emp.job_title or "",
                        }
                        for emp in team_employees
                    ],
                },
                request_id=request_id,
            )

        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            title = str(payload.get("title") or "").strip()
            if not title:
                raise ValidationError("يرجى إدخال عنوان المهمة.")
            description = str(payload.get("description") or "").strip()
            priority = str(payload.get("priority") or "normal").strip()
            if priority not in {"low", "normal", "high", "urgent"}:
                priority = "normal"
            due_str = str(payload.get("due_date") or "").strip()
            due_date = fields.Date.from_string(due_str[:10]) if due_str else today

            target_emp_id = int(payload.get("employee_id") or employee.id)
            if target_emp_id != employee.id and target_emp_id not in team_employees.ids:
                raise ValidationError("يمكنك إسناد المهام لنفسك أو لموظفي فريقك فقط.")

            row = Task.create({
                "title": title,
                "description": description,
                "employee_id": target_emp_id,
                "assigned_by_employee_id": employee.id,
                "priority": priority,
                "due_date": due_date,
                "state": "todo",
            })

            attachments = payload.get("attachments") or []
            if payload.get("attachment") and not attachments:
                attachments = [payload.get("attachment")]
            att_ids = []
            for att_payload in attachments[:5]:
                if not isinstance(att_payload, dict):
                    continue
                mimetype = str(att_payload.get("mimetype") or "application/octet-stream")[:128]
                if mimetype not in {"application/pdf", "image/jpeg", "image/png"}:
                    raise ValidationError("Only PDF, JPG and PNG attachments are allowed.")
                content = base64.b64decode(str(att_payload.get("data_base64") or ""), validate=True)
                if not content or len(content) > 8 * 1024 * 1024:
                    raise ValidationError("Each attachment must be smaller than 8 MB.")
                att = request.env["ir.attachment"].sudo().create({
                    "name": str(att_payload.get("name") or "task_attachment")[:255],
                    "datas": base64.b64encode(content),
                    "mimetype": mimetype,
                    "res_model": "hader.mobile.task",
                    "res_id": row.id,
                })
                att_ids.append(att.id)
            if att_ids:
                row.write({"attachment_ids": [(6, 0, att_ids)]})

            self._audit(session, "task_created", request_id, {
                "creator_id": employee.id,
                "assignee_id": target_emp_id,
                "task_id": row.id,
                "reference": row.name,
            })
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "task_validation_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(
            data=row.mobile_dto(),
            code=201,
            request_id=request_id,
        )

    @http.route(api_routes("/tasks/<int:task_id>/status"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def update_task_status(self, task_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        row = request.env["hader.mobile.task"].sudo().browse(task_id).exists()
        if not row or row.company_id != employee.company_id:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "task_not_found", "message": "Task not found."},
                code=404,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            new_state = str(payload.get("state") or "").strip()
            note = str(payload.get("note") or "").strip()
            row.mobile_update_status(employee, new_state, note)

            attachments = payload.get("attachments") or []
            if payload.get("attachment") and not attachments:
                attachments = [payload.get("attachment")]
            new_att_ids = list(row.attachment_ids.ids)
            for att_payload in attachments[:5]:
                if not isinstance(att_payload, dict):
                    continue
                mimetype = str(att_payload.get("mimetype") or "application/octet-stream")[:128]
                if mimetype not in {"application/pdf", "image/jpeg", "image/png"}:
                    raise ValidationError("Only PDF, JPG and PNG attachments are allowed.")
                content = base64.b64decode(str(att_payload.get("data_base64") or ""), validate=True)
                if not content or len(content) > 8 * 1024 * 1024:
                    raise ValidationError("Each attachment must be smaller than 8 MB.")
                att = request.env["ir.attachment"].sudo().create({
                    "name": str(att_payload.get("name") or "task_proof")[:255],
                    "datas": base64.b64encode(content),
                    "mimetype": mimetype,
                    "res_model": "hader.mobile.task",
                    "res_id": row.id,
                })
                new_att_ids.append(att.id)
            if attachments:
                row.write({"attachment_ids": [(6, 0, new_att_ids)]})

            self._audit(session, "task_status_updated", request_id, {
                "actor_id": employee.id,
                "task_id": row.id,
                "state": new_state,
            })
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "task_update_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(data=row.mobile_dto(), request_id=request_id)

    @http.route(api_routes("/tasks/attachments/<int:attachment_id>"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def task_attachment(self, attachment_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        attachment = request.env["ir.attachment"].sudo().browse(attachment_id).exists()
        if not attachment or attachment.res_model != "hader.mobile.task":
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "attachment_not_found", "message": "Attachment not found."},
                code=404,
                request_id=request_id,
            )
        row = request.env["hader.mobile.task"].sudo().browse(attachment.res_id).exists()
        if not row or row.company_id != employee.company_id:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "attachment_not_found", "message": "Attachment not found."},
                code=404,
                request_id=request_id,
            )
        content = base64.b64decode(attachment.datas or b"")
        return request.make_response(
            content,
            headers=[
                ("Content-Type", attachment.mimetype or "application/octet-stream"),
                ("Content-Disposition", f'inline; filename="{attachment.name}"'),
                ("X-Request-Id", request_id),
            ],
        )

    # =========================================================================
    # SALARY ADVANCES & LOANS (السلف المالية)
    # =========================================================================

    @http.route(api_routes("/loans"), type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def employee_loans(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        Loan = request.env["hader.mobile.loan"].sudo()

        if request.httprequest.method == "GET":
            rows = Loan.search(
                [("employee_id", "=", employee.id), ("active", "=", True)],
                limit=100,
                order="request_date desc, id desc",
            )
            approved_total = sum(r.amount for r in rows if r.state == "approved")
            pending_total = sum(r.amount for r in rows if r.state == "submitted")
            pending_count = sum(1 for r in rows if r.state == "submitted")
            approved_count = sum(1 for r in rows if r.state == "approved")
            rejected_count = sum(1 for r in rows if r.state == "rejected")
            currency = (
                employee.company_id.currency_id.symbol
                or employee.company_id.currency_id.name
                or "SAR"
            )
            return HaderMobileApiV1._response(
                data={
                    "summary": {
                        "approved_total": round(approved_total, 2),
                        "pending_total": round(pending_total, 2),
                        "pending_count": pending_count,
                        "approved_count": approved_count,
                        "rejected_count": rejected_count,
                        "currency": currency,
                    },
                    "items": [row.mobile_dto(locale) for row in rows],
                },
                request_id=request_id,
            )

        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            loan_type = str(payload.get("loan_type") or "advance").strip()
            if loan_type not in {"advance", "installment", "emergency"}:
                loan_type = "advance"
            amount = float(payload.get("amount") or 0.0)
            installments_count = int(payload.get("installments_count") or 1)
            reason = str(payload.get("reason") or "").strip()
            req_date_str = str(payload.get("request_date") or "").strip()
            req_date = date.fromisoformat(req_date_str[:10]) if req_date_str else date.today()
            ded_date_str = str(payload.get("deduction_start_date") or "").strip()
            ded_date = date.fromisoformat(ded_date_str[:10]) if ded_date_str else req_date

            if amount <= 0 or not reason:
                raise ValidationError(
                    "يرجى إدخال مبلغ السلفة الصحيح وسبب الطلب. / Valid loan amount and reason are required."
                )
            if installments_count < 1 or installments_count > 60:
                raise ValidationError(
                    "عدد الأقساط يجب أن يكون بين شهر واحد و 60 شهراً. / Installments must be between 1 and 60 months."
                )

            raw_attachments = payload.get("attachments") or []
            if payload.get("attachment") and isinstance(payload.get("attachment"), dict):
                raw_attachments = [payload.get("attachment")]
            validated_attachments = []
            for att in raw_attachments[:5]:
                if not isinstance(att, dict):
                    continue
                name = str(att.get("name") or "loan-document").strip()[:255]
                mimetype = str(att.get("mimetype") or "application/octet-stream")[:128]
                if mimetype not in {"application/pdf", "image/jpeg", "image/png"}:
                    raise ValidationError(
                        "يسمح فقط بمرفقات PDF أو JPG أو PNG. / Only PDF, JPG and PNG attachments are allowed."
                    )
                content = base64.b64decode(str(att.get("data_base64") or ""), validate=True)
                if not content or len(content) > 5 * 1024 * 1024:
                    raise ValidationError(
                        "حجم المرفق يجب ألا يتجاوز 5 ميجابايت. / Each attachment must be smaller than 5 MB."
                    )
                validated_attachments.append({
                    "name": name or "loan-attachment",
                    "datas": base64.b64encode(content),
                    "mimetype": mimetype,
                })

            loan = Loan.create({
                "employee_id": employee.id,
                "loan_type": loan_type,
                "request_date": req_date,
                "deduction_start_date": ded_date,
                "amount": amount,
                "installments_count": installments_count,
                "reason": reason,
            })
            created_att_ids = []
            for att_vals in validated_attachments:
                att_rec = request.env["ir.attachment"].sudo().create({
                    **att_vals,
                    "res_model": "hader.mobile.loan",
                    "res_id": loan.id,
                })
                created_att_ids.append(att_rec.id)

            partner = employee.work_contact_id
            loan.sudo().message_post(
                body=f"تم تقديم طلب سلفة مالية من تطبيق حاضر بواسطة {employee.name} بمبلغ {amount:.2f} على {installments_count} شهر.",
                author_id=partner.id if partner else None,
                attachment_ids=created_att_ids,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
            self._audit(session, "loan_request_submitted", request_id, {
                "employee_id": employee.id,
                "employee_name": employee.name,
                "loan_id": loan.id,
                "amount": amount,
                "installments_count": installments_count,
            })
            manager = (
                loan.manager_id
                or (
                    employee._get_mobile_approver_employee("expense_manager_id")
                    if hasattr(employee, "_get_mobile_approver_employee")
                    else employee.parent_id
                )
            )
            if manager and "hader.mobile.notification.inbox" in request.env:
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    manager,
                    "طلب سلفة جديد",
                    f"أرسل {employee.name} طلب سلفة ({loan.name} - {loan.type_label('ar')}) بمبلغ {amount:.2f}.",
                    "loan_submitted",
                    title_en="New loan request",
                    body_en=f"{employee.name} submitted a new loan request ({loan.name}) for {amount:.2f}.",
                )
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UserError, ValidationError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "loan_validation_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(data=loan.mobile_dto(locale), code=201, request_id=request_id)

    @http.route(api_routes("/loans/team"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def team_loans(self, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        emp_domain = (
            manager._mobile_team_domain("expense_manager_id")
            if hasattr(manager, "_mobile_team_domain")
            else [("parent_id", "=", manager.id), ("id", "!=", manager.id)]
        )
        team_emp_ids = request.env["hr.employee"].sudo().search(
            emp_domain + [("company_id", "=", manager.company_id.id)]
        ).ids
        rows = request.env["hader.mobile.loan"].sudo().search([
            "|",
            ("employee_id", "in", team_emp_ids),
            ("manager_id", "=", manager.id),
            ("employee_id", "!=", manager.id),
            ("company_id", "=", manager.company_id.id),
            ("state", "=", "submitted"),
            ("active", "=", True),
        ], limit=100, order="create_date desc, id desc")
        return HaderMobileApiV1._response(
            data={"items": [row.mobile_dto(locale) for row in rows]},
            request_id=request_id,
        )

    @http.route(api_routes("/loans/<int:loan_id>/review"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def review_loan(self, loan_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        manager = session.identity_id.employee_id
        locale = (request.httprequest.headers.get("Accept-Language") or "ar")[:2]
        loan = request.env["hader.mobile.loan"].sudo().browse(loan_id).exists()
        if not loan or not loan.active or loan.company_id != manager.company_id or not loan._is_approver(manager):
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "loan_not_found", "message": "Loan request not found."},
                code=404,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            decision = str(payload.get("decision") or "").strip()
            note = str(payload.get("note") or "").strip()
            loan.mobile_review(manager, decision, note)
            self._post_as_employee(
                loan,
                manager,
                f"تمت مراجعة طلب السلفة من تطبيق حاضر بواسطة المدير {manager.name}: "
                f"{'اعتماد وموافقة' if decision == 'approve' else 'رفض'}."
                + (f" ملاحظة: {note}" if note else ""),
            )
            self._audit(session, "loan_request_reviewed", request_id, {
                "manager_id": manager.id,
                "manager_name": manager.name,
                "employee_id": loan.employee_id.id,
                "employee_name": loan.employee_id.name,
                "loan_id": loan.id,
                "decision": decision,
            })
            if "hader.mobile.notification.inbox" in request.env:
                approved = decision == "approve"
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    loan.employee_id,
                    "تم اعتماد طلب السلفة" if approved else "تم رفض طلب السلفة",
                    f"وافق مديرك ({manager.name}) على طلب السلفة ({loan.name}) بمبلغ {loan.amount:.2f}."
                    if approved
                    else f"تم رفض طلب السلفة ({loan.name}). السبب: {note}",
                    "loan_result",
                    title_en="Loan request approved" if approved else "Loan request rejected",
                    body_en=f"Your manager ({manager.name}) approved your loan request ({loan.name}) for {loan.amount:.2f}."
                    if approved
                    else f"Your loan request ({loan.name}) was rejected. Reason: {note}",
                )
        except (UserError, ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "loan_review_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return HaderMobileApiV1._response(data=loan.mobile_dto(locale), request_id=request_id)

    @http.route(api_routes("/loans/attachments/<int:attachment_id>"), type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def loan_attachment(self, attachment_id, **_kwargs):
        request_id = HaderMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        attachment = request.env["ir.attachment"].sudo().browse(attachment_id).exists()
        if not attachment or attachment.res_model != "hader.mobile.loan":
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "attachment_not_found", "message": "Attachment not found."},
                code=404,
                request_id=request_id,
            )
        loan = request.env["hader.mobile.loan"].sudo().browse(attachment.res_id).exists()
        if not loan or (loan.employee_id != employee and not loan._is_approver(employee)):
            return HaderMobileApiV1._response(
                status="error",
                error={"code": "attachment_not_found", "message": "Attachment not found."},
                code=404,
                request_id=request_id,
            )
        content = base64.b64decode(attachment.datas or b"")
        return request.make_response(
            content,
            headers=[
                ("Content-Type", attachment.mimetype or "application/octet-stream"),
                ("Content-Disposition", f'inline; filename="{attachment.name}"'),
                ("X-Request-Id", request_id),
            ],
        )
