from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HaderMobileAnnouncement(models.Model):
    _name = "hader.mobile.announcement"
    _description = "Company Announcement & Circular (إعلانات وتعاميم الشركة)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "publish_date desc, id desc"

    name = fields.Char(
        string="عنوان الإعلان (عربي) / Title (AR)",
        required=True,
        tracking=True,
    )
    name_en = fields.Char(
        string="عنوان الإعلان (إنجليزي) / Title (EN)",
        tracking=True,
    )
    body = fields.Text(
        string="نص الإعلان أو التعميم (عربي) / Content (AR)",
        required=True,
        tracking=True,
    )
    body_en = fields.Text(
        string="نص الإعلان أو التعميم (إنجليزي) / Content (EN)",
        tracking=True,
    )
    priority = fields.Selection(
        [
            ("normal", "إعلان عام / General"),
            ("important", "تعميم هام / Important"),
            ("urgent", "تنبيه عاجل / Urgent"),
        ],
        string="الأهمية / Priority",
        default="normal",
        required=True,
        tracking=True,
    )
    publish_date = fields.Datetime(
        string="تاريخ ووقت البداية / Start Date & Time",
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
    expiry_date = fields.Datetime(
        string="تاريخ ووقت الانتهاء / End Date & Time",
        default=lambda self: fields.Datetime.now() + timedelta(days=1),
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="الشركة / Company",
        default=lambda self: self.env.company,
        required=True,
        index=True,
    )
    department_ids = fields.Many2many(
        "hr.department",
        string="الأقسام المستهدفة (فارغ = جميع الموظفين) / Target Departments",
    )
    active = fields.Boolean(default=True, tracking=True)

    @api.constrains("publish_date", "expiry_date")
    def _check_dates(self):
        for rec in self:
            if rec.publish_date and rec.expiry_date and rec.expiry_date <= rec.publish_date:
                raise ValidationError(
                    _(
                        "❌ لا يمكن أن يكون تاريخ ووقت الانتهاء قبل أو مساوياً لتاريخ ووقت البداية!\n"
                        "End date & time must be strictly after start date & time."
                    )
                )

    def action_broadcast_push(self):
        """Send push notification & inbox message to all targeted employees."""
        if "hader.mobile.notification.inbox" not in self.env:
            return True
        Inbox = self.env["hader.mobile.notification.inbox"].sudo()
        for rec in self:
            domain = [("company_id", "=", rec.company_id.id), ("active", "=", True)]
            if rec.department_ids:
                domain.append(("department_id", "in", rec.department_ids.ids))
            employees = self.env["hr.employee"].sudo().search(domain)
            for emp in employees:
                Inbox.notify_employee(
                    emp,
                    rec.name,
                    rec.body,
                    "announcement",
                    title_en=rec.name_en or rec.name,
                    body_en=rec.body_en or rec.body,
                )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "تم إرسال الإشعار / Notification Sent",
                "message": "تم إرسال التعميم كإشعار فوري لجميع الموظفين المستهدفين.",
                "type": "success",
                "sticky": False,
            },
        }

    def mobile_dto(self, locale="ar"):
        self.ensure_one()
        is_ar = (locale or "ar").startswith("ar")
        title = self.name if is_ar else (self.name_en or self.name)
        content = self.body if is_ar else (self.body_en or self.body)
        priority_label = {
            "normal": "إعلان عام" if is_ar else "Announcement",
            "important": "تعميم هام" if is_ar else "Important",
            "urgent": "تنبيه عاجل" if is_ar else "Urgent",
        }.get(self.priority, self.priority)
        return {
            "id": self.id,
            "title": title or "",
            "body": content or "",
            "priority": self.priority or "normal",
            "priority_label": priority_label,
            "publish_date": self.publish_date.isoformat() if self.publish_date else "",
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else "",
        }
