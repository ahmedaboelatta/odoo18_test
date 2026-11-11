from datetime import datetime
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


CUSTODY_ITEM_TYPES = [
    ("laptop", "لابتوب / حاسب محمول (Laptop / PC)"),
    ("phone", "جوال عمل (Mobile Phone)"),
    ("sim", "شريحة اتصال / بيانات (SIM / Data Card)"),
    ("vehicle", "سيارة / مركبة (Company Vehicle)"),
    ("card", "بطاقة عمل / مفاتيح (Access Card / Keys)"),
    ("tools", "أجهزة ومعدات عمل (Work Equipment & Tools)"),
    ("other", "عهدة أخرى (Other Custody)"),
]

CUSTODY_TYPE_LABELS = {
    "laptop": ("لابتوب / حاسب محمول", "Laptop / PC"),
    "phone": ("جوال عمل", "Mobile Phone"),
    "sim": ("شريحة اتصال / بيانات", "SIM / Data Card"),
    "vehicle": ("سيارة / مركبة", "Company Vehicle"),
    "card": ("بطاقة عمل / مفاتيح", "Access Card / Keys"),
    "tools": ("أجهزة ومعدات عمل", "Work Equipment & Tools"),
    "other": ("عهدة أخرى", "Other Custody"),
}


class HaderMobileCustody(models.Model):
    _name = "hader.mobile.custody"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Employee Personal Custody & Asset (عهدة الموظف الشخصية)"
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="رقم قيد العهدة / Reference",
        required=True,
        readonly=True,
        default="New",
        copy=False,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="الموظف / Employee",
        required=True,
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="employee_id.company_id",
        store=True,
        index=True,
    )
    manager_id = fields.Many2one(
        "hr.employee",
        related="employee_id.parent_id",
        string="المدير المباشر / Direct Manager",
        store=True,
        readonly=True,
    )
    item_type = fields.Selection(
        CUSTODY_ITEM_TYPES,
        string="نوع العهدة / Asset Type",
        required=True,
        default="laptop",
        tracking=True,
    )
    title = fields.Char(
        string="اسم العهدة / الموديل / Asset Name",
        required=True,
        tracking=True,
    )
    serial_number = fields.Char(
        string="الرقم التسلسلي / رقم الشريحة / اللوحة / Serial or Number",
        tracking=True,
    )
    request_date = fields.Date(
        string="تاريخ الطلب / التسجيل / Request Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    assigned_date = fields.Date(
        string="تاريخ التسليم للموظف / Handover Date",
        tracking=True,
    )
    return_date = fields.Date(
        string="تاريخ الإرجاع / إخلاء الطرف / Return Date",
        tracking=True,
    )
    notes = fields.Text(string="المواصفات وحالة العهدة والملاحظات / Notes & Condition")
    state = fields.Selection(
        [
            ("submitted", "بانتظار موافقة المدير / Waiting Manager"),
            ("manager_approved", "معتمد من المدير (بانتظار التسليم) / Manager Approved"),
            ("assigned", "مسلّمة في عهدة الموظف / Active in Custody"),
            ("return_requested", "طلب إخلاء / إرجاع عهدة / Return Requested"),
            ("returned", "تم إرجاع العهدة وإخلاء الطرف / Returned"),
            ("rejected", "مرفوض / Rejected"),
        ],
        string="الحالة / Status",
        default="submitted",
        required=True,
        index=True,
        tracking=True,
    )
    manager_reviewed_by_id = fields.Many2one(
        "hr.employee",
        string="تمت مراجعة المدير بواسطة / Reviewed By Manager",
        readonly=True,
    )
    manager_reviewed_at = fields.Datetime(
        string="تاريخ مراجعة المدير / Manager Reviewed At",
        readonly=True,
    )
    manager_review_note = fields.Text(
        string="ملاحظة المدير المباشر / Manager Note",
        readonly=True,
    )
    admin_note = fields.Text(
        string="ملاحظة الإدارة / إخلاء الطرف / Admin Note",
        tracking=True,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "hader_mobile_custody_ir_attachment_rel",
        "custody_id",
        "attachment_id",
        string="صور ومستندات العهدة / Custody Attachments",
    )
    attachment_count = fields.Integer(
        string="عدد المرفقات",
        compute="_compute_attachment_count",
    )
    active = fields.Boolean(default=True)

    @api.depends("attachment_ids")
    def _compute_attachment_count(self):
        for rec in self:
            rec.attachment_count = len(rec.attachment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        ym = fields.Date.context_today(self).strftime("%Y/%m")
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                seq = self.env["ir.sequence"].next_by_code("hader.mobile.custody") or "00001"
                num = seq.split("-")[-1].split("/")[-1]
                vals["name"] = f"CUS/{ym}/{num}"
            if vals.get("state") == "assigned" and not vals.get("assigned_date"):
                vals["assigned_date"] = fields.Date.context_today(self)
        records = super().create(vals_list)
        for rec in records:
            if rec.state == "assigned":
                rec._notify_employee_decision(
                    "تم تسليمك عهدة شخصية جديدة",
                    f"تم تسجيل وتسليم عهدة ({rec.title}) برقم {rec.name} على ملفك الشخصي.",
                    "New custody item assigned to you",
                    f"Custody item ({rec.title}) ref {rec.name} has been assigned to you.",
                )
        return records

    def _get_approver_employee(self):
        self.ensure_one()
        emp = self.employee_id
        if hasattr(emp, "_get_mobile_approver_employee"):
            return emp._get_mobile_approver_employee("expense_manager_id")
        return emp.parent_id

    def _is_approver(self, manager_employee):
        self.ensure_one()
        emp = self.employee_id
        if hasattr(emp, "_is_mobile_approver"):
            return emp._is_mobile_approver(manager_employee, "expense_manager_id")
        return bool(emp.parent_id and emp.parent_id.id == manager_employee.id)

    def _notify_employee_decision(self, title_ar, body_ar, title_en, body_en):
        if "hader.mobile.notification.inbox" not in self.env:
            return
        Inbox = self.env["hader.mobile.notification.inbox"].sudo()
        for rec in self:
            Inbox.notify_employee(
                rec.employee_id,
                title_ar,
                body_ar,
                "custody_result",
                title_en=title_en,
                body_en=body_en,
            )

    def action_manager_approve(self):
        for rec in self:
            if rec.state != "submitted":
                raise ValidationError(_("Only submitted custody requests can be manager-approved."))
            rec.write({
                "state": "manager_approved",
                "manager_reviewed_at": fields.Datetime.now(),
            })
            rec.message_post(
                body=_("تم اعتماد طلب العهدة من المدير، وبانتظار تسليم العهدة من الإدارة."),
                subtype_xmlid="mail.mt_note",
            )
            rec._notify_employee_decision(
                "موافقة المدير على طلب العهدة",
                f"وافق المدير المباشر على طلب العهدة ({rec.title}) برقم {rec.name} وتم رفعه للإدارة للتسليم.",
                "Custody request approved by manager",
                f"Your manager approved custody request ({rec.title}) {rec.name}.",
            )
        return True

    def action_assign(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.write({
                "state": "assigned",
                "assigned_date": rec.assigned_date or today,
            })
            rec.message_post(
                body=_("تم تسليم العهدة للموظف وتفعيلها في ذمته."),
                subtype_xmlid="mail.mt_note",
            )
            rec._notify_employee_decision(
                "تم تسليم واعتماد العهدة الشخصية",
                f"تم تسليم وتفعيل العهدة ({rec.title}) برقم {rec.name} في ملف عهدك الشخصية.",
                "Custody item handed over & active",
                f"Custody item ({rec.title}) {rec.name} is now active in your custody.",
            )
        return True

    def action_mark_returned(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.write({
                "state": "returned",
                "return_date": rec.return_date or today,
            })
            rec.message_post(
                body=_("تم استلام العهدة من الموظف وإخلاء طرفه منها."),
                subtype_xmlid="mail.mt_note",
            )
            rec._notify_employee_decision(
                "تم إخلاء طرفك من العهدة",
                f"تم تأكيد استلام وإخلاء طرفك من العهدة ({rec.title}) برقم {rec.name}.",
                "Custody item returned & cleared",
                f"Your custody item ({rec.title}) {rec.name} has been marked as returned.",
            )
        return True

    def action_reject(self):
        for rec in self:
            rec.write({"state": "rejected"})
            reason_suffix = f" السبب: {rec.admin_note}" if rec.admin_note else ""
            rec.message_post(
                body=_("تم رفض طلب العهدة.%s") % reason_suffix,
                subtype_xmlid="mail.mt_note",
            )
            rec._notify_employee_decision(
                "تم رفض طلب العهدة",
                f"تم رفض طلب العهدة ({rec.title}) برقم {rec.name}.{reason_suffix}",
                "Custody request rejected",
                f"Your custody request ({rec.title}) {rec.name} was rejected.{reason_suffix}",
            )
        return True

    def mobile_request_return(self, employee, note=""):
        self.ensure_one()
        if self.employee_id.id != employee.id:
            raise ValidationError(_("You can only request return for your own custody items."))
        if self.state != "assigned":
            raise ValidationError(_("Only active custody items can be requested for return."))
        clean_note = (note or "").strip()
        updated_notes = self.notes or ""
        if clean_note:
            updated_notes = f"{updated_notes}\n[طلب إخلاء/إرجاع]: {clean_note}".strip()
        self.sudo().write({
            "state": "return_requested",
            "notes": updated_notes,
        })
        self.sudo().message_post(
            body=_("طلب الموظف %s إرجاع / إخلاء العهدة من التطبيق. ملاحظة: %s")
            % (employee.name, clean_note or "—"),
            subtype_xmlid="mail.mt_note",
        )
        manager = self._get_approver_employee()
        if manager and "hader.mobile.notification.inbox" in self.env:
            self.env["hader.mobile.notification.inbox"].sudo().notify_employee(
                manager,
                "طلب إخلاء / إرجاع عهدة",
                f"طلب {employee.name} إرجاع العهدة ({self.title}) برقم {self.name}.",
                "custody_submitted",
                title_en="Custody return request",
                body_en=f"{employee.name} requested to return custody item ({self.title}) {self.name}.",
            )
        return True

    def mobile_review(self, manager_employee, decision, note=""):
        self.ensure_one()
        if not self._is_approver(manager_employee):
            raise ValidationError(_("You can only review custody requests for your team."))
        if self.state not in ("submitted", "return_requested"):
            raise ValidationError(_("This custody request has already been reviewed."))
        if decision not in ("approve", "reject"):
            raise ValidationError(_("Decision must be approve or reject."))
        clean_note = (note or "").strip()
        if decision == "reject" and not clean_note:
            raise ValidationError(_("يرجى كتابة سبب الرفض. / A rejection reason is required."))

        is_return = self.state == "return_requested"
        if decision == "approve":
            if is_return:
                self.sudo().write({
                    "state": "returned",
                    "return_date": fields.Date.context_today(self),
                    "manager_reviewed_by_id": manager_employee.id,
                    "manager_reviewed_at": fields.Datetime.now(),
                    "manager_review_note": clean_note,
                })
                self._notify_employee_decision(
                    "تم اعتماد إخلاء العهدة",
                    f"اعتمد مديرك {manager_employee.name} إرجاع وإخلاء طرفك من العهدة ({self.title}) برقم {self.name}.",
                    "Custody return approved",
                    f"{manager_employee.name} approved the return of custody item ({self.title}) {self.name}.",
                )
            else:
                self.sudo().write({
                    "state": "manager_approved",
                    "manager_reviewed_by_id": manager_employee.id,
                    "manager_reviewed_at": fields.Datetime.now(),
                    "manager_review_note": clean_note,
                })
                self._notify_employee_decision(
                    "موافقة المدير على طلب العهدة",
                    f"وافق مديرك المباشر {manager_employee.name} على طلب العهدة ({self.title}) برقم {self.name}.",
                    "Custody request approved by manager",
                    f"{manager_employee.name} approved your custody request ({self.title}) {self.name}.",
                )
        else:
            if is_return:
                self.sudo().write({
                    "state": "assigned",
                    "manager_reviewed_by_id": manager_employee.id,
                    "manager_reviewed_at": fields.Datetime.now(),
                    "manager_review_note": clean_note,
                })
                self._notify_employee_decision(
                    "تم رفض طلب إخلاء العهدة",
                    f"رفض {manager_employee.name} طلب إخلاء العهدة ({self.title}). السبب: {clean_note}",
                    "Custody return rejected",
                    f"{manager_employee.name} rejected return of ({self.title}). Reason: {clean_note}",
                )
            else:
                self.sudo().write({
                    "state": "rejected",
                    "manager_reviewed_by_id": manager_employee.id,
                    "manager_reviewed_at": fields.Datetime.now(),
                    "manager_review_note": clean_note,
                })
                self._notify_employee_decision(
                    "تم رفض طلب العهدة",
                    f"رفض مديرك المباشر {manager_employee.name} طلب العهدة ({self.title}). السبب: {clean_note}",
                    "Custody request rejected",
                    f"{manager_employee.name} rejected your custody request ({self.title}). Reason: {clean_note}",
                )
        return True

    def mobile_dto(self, locale="ar"):
        self.ensure_one()
        ar_label, en_label = CUSTODY_TYPE_LABELS.get(
            self.item_type, ("عهدة أخرى", "Other Custody")
        )
        return {
            "id": self.id,
            "reference": self.name,
            "employee_id": self.employee_id.id,
            "employee_name": self.employee_id.name or "",
            "item_type": self.item_type,
            "item_type_label": en_label if locale == "en" else ar_label,
            "item_type_label_ar": ar_label,
            "item_type_label_en": en_label,
            "title": self.title or "",
            "serial_number": self.serial_number or "",
            "request_date": self.request_date.isoformat() if self.request_date else None,
            "assigned_date": self.assigned_date.isoformat() if self.assigned_date else None,
            "return_date": self.return_date.isoformat() if self.return_date else None,
            "notes": self.notes or "",
            "state": self.state,
            "manager_name": self.manager_id.name if self.manager_id else "",
            "manager_reviewed_by": self.manager_reviewed_by_id.name if self.manager_reviewed_by_id else "",
            "manager_reviewed_at": self.manager_reviewed_at.isoformat() if self.manager_reviewed_at else None,
            "manager_review_note": self.manager_review_note or "",
            "admin_note": self.admin_note or "",
            "created_at": self.create_date.isoformat() if self.create_date else None,
            "attachments": [
                {
                    "id": att.id,
                    "name": att.name,
                    "mimetype": att.mimetype or "application/octet-stream",
                    "size": att.file_size or 0,
                }
                for att in self.attachment_ids.sudo()
            ],
        }
