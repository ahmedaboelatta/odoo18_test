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
    active = fields.Boolean(
        string="نشط / Active",
        default=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("scheduled", "مجدول / Scheduled"),
            ("active", "نشط / Active"),
            ("expired", "غير نشط (منتهي) / Inactive"),
        ],
        string="حالة التعميم / Status",
        compute="_compute_state",
        store=True,
        default="active",
        tracking=True,
    )

    @api.depends("active", "publish_date", "expiry_date")
    def _compute_state(self):
        now = fields.Datetime.now()
        for rec in self:
            if not rec.active or (rec.expiry_date and rec.expiry_date <= now):
                rec.state = "expired"
            elif rec.publish_date and rec.publish_date > now:
                rec.state = "scheduled"
            else:
                rec.state = "active"

    @api.onchange("publish_date", "expiry_date", "active")
    def _onchange_dates_or_active(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.expiry_date and rec.expiry_date <= now:
                rec.active = False
                rec.state = "expired"
            elif not rec.active:
                rec.state = "expired"
            elif rec.publish_date and rec.publish_date > now:
                rec.state = "scheduled"
            else:
                rec.state = "active"

    @api.model
    def _sync_expired_announcements(self):
        """Automatically mark expired announcements as active=False and state='expired',
        and promote scheduled announcements whose publish_date has arrived."""
        now = fields.Datetime.now()
        self.env.cr.execute(
            """
            UPDATE hader_mobile_announcement
               SET active = FALSE,
                   state = 'expired'
             WHERE (expiry_date IS NOT NULL AND expiry_date <= %s AND (active IS TRUE OR state != 'expired'))
                OR (active IS FALSE AND (state IS NULL OR state != 'expired'))
            """,
            (now,),
        )
        if self.env.cr.rowcount:
            self.env.invalidate_all()
        self.env.cr.execute(
            """
            UPDATE hader_mobile_announcement
               SET state = 'active'
             WHERE active IS TRUE
               AND (publish_date IS NULL OR publish_date <= %s)
               AND (expiry_date IS NULL OR expiry_date > %s)
               AND (state IS NULL OR state != 'active')
            """,
            (now, now),
        )
        if self.env.cr.rowcount:
            self.env.invalidate_all()
        self.env.cr.execute(
            """
            UPDATE hader_mobile_announcement
               SET state = 'scheduled'
             WHERE active IS TRUE
               AND publish_date IS NOT NULL
               AND publish_date > %s
               AND (expiry_date IS NULL OR expiry_date > %s)
               AND (state IS NULL OR state != 'scheduled')
            """,
            (now, now),
        )
        if self.env.cr.rowcount:
            self.env.invalidate_all()

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        self._sync_expired_announcements()
        if "active_test" not in self.env.context:
            self = self.with_context(active_test=False)
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

    def read(self, fields=None, load="_classic_read"):
        self.env["hader.mobile.announcement"]._sync_expired_announcements()
        return super().read(fields=fields, load=load)

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            exp = fields.Datetime.to_datetime(vals.get("expiry_date")) if vals.get("expiry_date") else None
            if exp and exp <= now:
                vals["active"] = False
                vals["state"] = "expired"
        records = super().create(vals_list)
        records._compute_state()
        return records

    def write(self, vals):
        now = fields.Datetime.now()
        if "expiry_date" in vals and vals["expiry_date"] and "active" not in vals:
            exp = fields.Datetime.to_datetime(vals["expiry_date"])
            if exp and exp > now:
                vals["active"] = True
            elif exp and exp <= now:
                vals["active"] = False
        res = super().write(vals)
        self._sync_expired_announcements()
        return res

    def action_activate(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.expiry_date and rec.expiry_date <= now:
                raise ValidationError(
                    _(
                        "❌ لا يمكن تفعيل التعميم لأن تاريخ ووقت الانتهاء قد مضى بالفعل. يرجى تمديد تاريخ ووقت الانتهاء أولاً.\n"
                        "Cannot activate an expired announcement. Please extend the End Date & Time first."
                    )
                )
            rec.write({"active": True})

    def action_deactivate(self):
        self.write({"active": False, "state": "expired"})

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
