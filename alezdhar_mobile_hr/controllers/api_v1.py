from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request

from odoo.addons.alezdhar_mobile_core.controllers.api_v1 import API_PREFIX, AlezdharMobileApiV1


class AlezdharPayslipApiV1(http.Controller):
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
    def _slip(employee, slip_id=None):
        domain = [
            ("employee_id", "=", employee.id),
            ("company_id", "=", employee.company_id.id),
            ("state", "=", "done"),
        ]
        if slip_id is not None:
            domain.append(("id", "=", slip_id))
        return request.env["hr.payslip"].sudo().search(domain, limit=1 if slip_id else 50,
                                                        order="date_to desc, id desc")

    @staticmethod
    def _dto(slip, details=False):
        value = {
            "id": slip.id,
            "name": slip.name or slip.number or "Payslip",
            "number": slip.number or "",
            "date_from": slip.date_from.isoformat(),
            "date_to": slip.date_to.isoformat(),
            "state": slip.state,
        }
        if details:
            value["lines"] = [{
                "name": line.name,
                "code": line.code or "",
                "total": line.total,
                "category": line.category_id.name or "",
            } for line in slip.line_ids.filtered(lambda row: row.appears_on_payslip)]
        return value

    @http.route(API_PREFIX + "/payslips", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def payslips(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        rows = self._slip(session.identity_id.employee_id)
        return AlezdharMobileApiV1._response(
            data={"items": [self._dto(row) for row in rows]}, request_id=request_id
        )

    @http.route(API_PREFIX + "/payslips/<int:slip_id>", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def payslip(self, slip_id, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        slip = self._slip(session.identity_id.employee_id, slip_id)
        if not slip:
            return AlezdharMobileApiV1._response(
                status="error", error={"code": "payslip_not_found", "message": "Payslip not found."},
                code=404, request_id=request_id,
            )
        return AlezdharMobileApiV1._response(data=self._dto(slip, details=True), request_id=request_id)

    @http.route(API_PREFIX + "/payslips/<int:slip_id>/pdf", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def payslip_pdf(self, slip_id, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session(request_id)
        if error:
            return error
        employee = session.identity_id.employee_id
        slip = self._slip(employee, slip_id)
        if not slip:
            return AlezdharMobileApiV1._response(
                status="error", error={"code": "payslip_not_found", "message": "Payslip not found."},
                code=404, request_id=request_id,
            )
        pdf, _ = request.env.ref("payroll.action_report_payslip").sudo()._render_qweb_pdf([slip.id])
        request.env["alezdhar.mobile.audit"].sudo().create({
            "identity_id": session.identity_id.id,
            "company_id": employee.company_id.id,
            "event_type": "payslip_pdf_downloaded",
            "request_id": request_id,
            "outcome": "success",
            "metadata_json": '{"payslip_id": %d, "employee_id": %d}' % (slip.id, employee.id),
        })
        return request.make_response(pdf, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", 'attachment; filename="payslip-%s.pdf"' % slip.id),
        ])
