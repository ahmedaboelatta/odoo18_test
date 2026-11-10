import base64
import binascii
import json
from datetime import date

from odoo import http
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
            manager = employee.parent_id
            if manager and "hader.mobile.notification.inbox" in request.env:
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    manager,
                    "طلب إجازة جديد",
                    f"أرسل {employee.name} طلب إجازة جديدًا.",
                    "leave_submitted",
                    title_en="New time-off request",
                    body_en=f"{employee.name} submitted a new time-off request.",
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
        if not leave or (leave.employee_id != employee and leave.employee_id.parent_id != employee):
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
        rows = request.env["hr.leave"].sudo().search([
            ("employee_id.parent_id", "=", manager.id),
            ("employee_id", "!=", manager.id),
            ("employee_id.company_id", "=", manager.company_id.id),
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
        leave = request.env["hr.leave"].sudo().search([
            ("id", "=", leave_id),
            ("employee_id.parent_id", "=", manager.id),
            ("employee_id", "!=", manager.id),
            ("employee_id.company_id", "=", manager.company_id.id),
        ], limit=1)
        if not leave:
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
                    f"أرسل {employee.name} طلب خدمة جديد ({service.name}).",
                    "announcement",
                    title_en="New service request",
                    body_en=f"{employee.name} submitted a new service request ({service.name}).",
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
                    "announcement",
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
            manager = employee.parent_id
            if manager and "hader.mobile.notification.inbox" in request.env:
                request.env["hader.mobile.notification.inbox"].notify_employee(
                    manager,
                    "طلب مصاريف جديد",
                    f"أرسل {employee.name} طلب صرف مصاريف ({title}) بمبلغ {amount:.2f}.",
                    "expense_submitted",
                    title_en="New expense request",
                    body_en=f"{employee.name} submitted a new expense request ({title}) for {amount:.2f}.",
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
        if not expense or (expense.employee_id != employee and expense.employee_id.parent_id != employee):
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
        rows = request.env["hader.mobile.expense"].sudo().search([
            ("employee_id.parent_id", "=", manager.id),
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
        expense = request.env["hader.mobile.expense"].sudo().search([
            ("id", "=", expense_id),
            ("employee_id.parent_id", "=", manager.id),
            ("employee_id", "!=", manager.id),
            ("company_id", "=", manager.company_id.id),
        ], limit=1)
        if not expense:
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
