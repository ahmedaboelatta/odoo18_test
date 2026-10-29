from odoo import api, models


class AlezdharAttendanceCorrection(models.Model):
    _inherit = "alezdhar.attendance.correction"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Inbox = self.env["alezdhar.mobile.notification.inbox"]
        for record in records:
            manager = record.employee_id.parent_id
            if manager:
                Inbox.notify_employee(
                    manager,
                    "طلب تصحيح حضور جديد",
                    f"أرسل {record.employee_id.name} طلبًا لتعديل الحضور.",
                    "correction_submitted",
                    record,
                    title_en="New attendance correction request",
                    body_en=f"{record.employee_id.name} submitted an attendance correction request.",
                )
        return records

    def mobile_review(self, manager_employee, decision, note=None):
        result = super().mobile_review(manager_employee, decision, note)
        for record in self:
            approved = record.state == "approved"
            self.env["alezdhar.mobile.notification.inbox"].notify_employee(
                record.employee_id,
                "تم قبول طلب تصحيح الحضور" if approved else "تم رفض طلب تصحيح الحضور",
                "تم تحديث سجل حضورك بناءً على الطلب." if approved
                else f"سبب الرفض: {record.review_note or '-'}",
                "correction_result",
                record,
                title_en="Attendance correction approved" if approved else "Attendance correction rejected",
                body_en="Your attendance record was updated based on the request." if approved
                else f"Rejection reason: {record.review_note or '-'}",
            )
        return result
