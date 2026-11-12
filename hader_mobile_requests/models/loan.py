import base64

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


LOAN_TYPE_LABELS = {
    "advance": ("سلفة راتب", "Salary Advance"),
    "installment": ("سلفة مقسطة", "Installment Loan"),
    "emergency": ("سلفة طارئة", "Emergency Advance"),
}


class HaderMobileLoan(models.Model):
    _name = "hader.mobile.loan"
    _description = "Employee Mobile Salary Advance / Loan Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="رقم الطلب / Reference",
        default=lambda self: _("New"),
        readonly=True,
        copy=False,
        tracking=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="الموظف / Employee",
        required=True,
        index=True,
        ondelete="restrict",
        tracking=True,
    )
    manager_id = fields.Many2one(
        "hr.employee",
        compute="_compute_manager_id",
        string="المدير المعتمد / Approving Manager",
        store=True,
        readonly=False,
    )
    company_id = fields.Many2one(
        "res.company",
        related="employee_id.company_id",
        string="الشركة / Company",
        store=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        string="العملة / Currency",
        store=True,
        readonly=True,
    )
    loan_type = fields.Selection(
        [
            ("advance", "سلفة راتب / Salary Advance"),
            ("installment", "سلفة مقسطة / Installment Loan"),
            ("emergency", "سلفة طارئة / Emergency Advance"),
        ],
        string="نوع السلفة / Loan Type",
        default="advance",
        required=True,
        tracking=True,
    )
    request_date = fields.Date(
        string="تاريخ الطلب / Request Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    deduction_start_date = fields.Date(
        string="تاريخ بداية الاستقطاع / Deduction Start Date",
        default=fields.Date.context_today,
        tracking=True,
    )
    amount = fields.Monetary(
        string="مبلغ السلفة / Loan Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    installments_count = fields.Integer(
        string="عدد الأقساط (بالأشهر) / Installment Months",
        default=1,
        required=True,
        tracking=True,
    )
    installment_amount = fields.Monetary(
        string="قيمة القسط الشهري / Monthly Installment",
        currency_field="currency_id",
        compute="_compute_installment_amount",
        store=True,
    )
    reason = fields.Text(
        string="سبب الطلب والملاحظات / Reason & Notes",
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("submitted", "بانتظار موافقة المدير / Waiting Manager"),
            ("approved", "معتمدة / Approved"),
            ("rejected", "مرفوضة / Rejected"),
        ],
        string="الحالة / Status",
        default="submitted",
        required=True,
        tracking=True,
        index=True,
    )
    review_note = fields.Text(
        string="ملاحظة الاعتماد أو سبب الرفض / Review Note",
        tracking=True,
    )
    reviewed_by_id = fields.Many2one(
        "hr.employee",
        string="تمت المراجعة بواسطة / Reviewed By",
        readonly=True,
        ondelete="set null",
    )
    reviewed_at = fields.Datetime(
        string="تاريخ المراجعة / Reviewed At",
        readonly=True,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        compute="_compute_attachments",
        string="المرفقات / Attachments",
    )
    attachment_count = fields.Integer(
        compute="_compute_attachments",
        string="عدد المرفقات / Attachments Count",
    )
    active = fields.Boolean(default=True, tracking=True)

    @api.constrains("amount", "installments_count")
    def _check_amount_and_installments(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(
                    _("مبلغ السلفة يجب أن يكون أكبر من الصفر. / Loan amount must be greater than zero.")
                )
            if rec.installments_count < 1 or rec.installments_count > 60:
                raise ValidationError(
                    _("عدد الأقساط يجب أن يكون بين شهر واحد و 60 شهراً. / Installments must be between 1 and 60 months.")
                )

    @api.depends("amount", "installments_count")
    def _compute_installment_amount(self):
        for rec in self:
            months = max(1, int(rec.installments_count or 1))
            rec.installment_amount = round(float(rec.amount or 0.0) / months, 2)

    def _compute_attachments(self):
        Attachment = self.env["ir.attachment"].sudo()
        for rec in self:
            atts = Attachment.search([
                ("res_model", "=", "hader.mobile.loan"),
                ("res_id", "=", rec.id),
            ])
            rec.attachment_ids = atts
            rec.attachment_count = len(atts)

    @api.depends("employee_id", "employee_id.parent_id")
    def _compute_manager_id(self):
        for rec in self:
            if rec.employee_id and hasattr(rec.employee_id, "_get_mobile_approver_employee"):
                rec.manager_id = rec.employee_id._get_mobile_approver_employee("expense_manager_id")
            elif rec.employee_id:
                rec.manager_id = rec.employee_id.parent_id
            else:
                rec.manager_id = False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.name in (False, _("New"), "New"):
                dt = record.request_date or fields.Date.context_today(record)
                record.name = f"LOAN/{dt.year:04d}/{dt.month:02d}/{record.id:05d}"
        return records

    def type_label(self, locale="ar"):
        self.ensure_one()
        ar_label, en_label = LOAN_TYPE_LABELS.get(self.loan_type, ("سلفة مالية", "Salary Advance"))
        return en_label if str(locale or "ar").startswith("en") else ar_label

    def _is_approver(self, manager_employee):
        self.ensure_one()
        if not manager_employee or self.employee_id == manager_employee:
            return False
        if self.manager_id == manager_employee or self.employee_id.parent_id == manager_employee:
            return True
        if hasattr(self.employee_id, "_is_mobile_approver"):
            if self.employee_id._is_mobile_approver(manager_employee, "expense_manager_id"):
                return True
            if self.employee_id._is_mobile_approver(manager_employee, "leave_manager_id"):
                return True
        return False

    def mobile_dto(self, locale="ar"):
        self.ensure_one()
        attachments = self.env["ir.attachment"].sudo().search([
            ("res_model", "=", "hader.mobile.loan"),
            ("res_id", "=", self.id),
        ])
        currency = self.currency_id.symbol or self.currency_id.name or "SAR"
        return {
            "id": self.id,
            "reference": self.name or "",
            "loan_type": self.loan_type or "advance",
            "loan_type_name": self.type_label(locale),
            "request_date": self.request_date.isoformat() if self.request_date else None,
            "deduction_start_date": (
                self.deduction_start_date.isoformat() if self.deduction_start_date else None
            ),
            "amount": round(float(self.amount or 0.0), 2),
            "installments_count": int(self.installments_count or 1),
            "installment_amount": round(float(self.installment_amount or 0.0), 2),
            "currency": currency,
            "reason": self.reason or "",
            "state": self.state,
            "employee_id": self.employee_id.id,
            "employee_name": self.employee_id.name or "",
            "manager_name": self.manager_id.name if self.manager_id else "",
            "reviewed_by_name": self.reviewed_by_id.name if self.reviewed_by_id else "",
            "review_note": self.review_note or "",
            "created_at": self.create_date.isoformat() if self.create_date else None,
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

    def mobile_review(self, manager_employee, decision, note=None):
        """Approve or reject loan request by the employee's manager from the mobile app."""
        self.ensure_one()
        if not self._is_approver(manager_employee):
            raise ValidationError(
                _("فقط المدير المباشر أو المعتمد للموظف يمكنه مراجعة طلب السلفة. / Only the employee's manager can review this loan request.")
            )
        if self.state != "submitted":
            raise ValidationError(
                _("تمت مراجعة طلب السلفة هذا مسبقاً. / This loan request has already been reviewed.")
            )
        if decision not in ("approve", "reject"):
            raise ValidationError(_("قرار المراجعة غير صالح. / Invalid review decision."))
        cleaned_note = (note or "").strip()
        if decision == "reject" and not cleaned_note:
            raise ValidationError(_("يرجى إدخال سبب رفض السلفة. / A rejection reason is required."))

        approved = decision == "approve"
        self.sudo().write({
            "state": "approved" if approved else "rejected",
            "review_note": cleaned_note or (_("تم الاعتماد من المدير %s") % manager_employee.name),
            "reviewed_by_id": manager_employee.id,
            "reviewed_at": fields.Datetime.now(),
        })
        return True

    def action_approve(self):
        Inbox = (
            self.env["hader.mobile.notification.inbox"].sudo()
            if "hader.mobile.notification.inbox" in self.env
            else False
        )
        for rec in self:
            if rec.state == "approved":
                continue
            reviewer_emp = self.env.user.employee_id or rec.manager_id
            rec.write({
                "state": "approved",
                "reviewed_by_id": reviewer_emp.id if reviewer_emp else False,
                "reviewed_at": fields.Datetime.now(),
                "review_note": rec.review_note or (_("تم الاعتماد بواسطة %s") % self.env.user.name),
            })
            if Inbox and rec.employee_id:
                Inbox.notify_employee(
                    rec.employee_id,
                    "تم اعتماد طلب السلفة",
                    f"تمت الموافقة على طلب السلفة ({rec.name}) بمبلغ {rec.amount:.2f}.",
                    "loan_result",
                    title_en="Loan request approved",
                    body_en=f"Your loan request ({rec.name}) for {rec.amount:.2f} has been approved.",
                )

    def action_reject(self):
        Inbox = (
            self.env["hader.mobile.notification.inbox"].sudo()
            if "hader.mobile.notification.inbox" in self.env
            else False
        )
        for rec in self:
            reason = (rec.review_note or "").strip()
            if not reason:
                raise ValidationError(
                    _("يرجى كتابة سبب الرفض في حقل (ملاحظة الاعتماد أو سبب الرفض) قبل رفض السلفة.")
                )
            reviewer_emp = self.env.user.employee_id or rec.manager_id
            rec.write({
                "state": "rejected",
                "reviewed_by_id": reviewer_emp.id if reviewer_emp else False,
                "reviewed_at": fields.Datetime.now(),
            })
            if Inbox and rec.employee_id:
                Inbox.notify_employee(
                    rec.employee_id,
                    "تم رفض طلب السلفة",
                    f"تم رفض طلب السلفة ({rec.name}). السبب: {reason}",
                    "loan_result",
                    title_en="Loan request rejected",
                    body_en=f"Your loan request ({rec.name}) was rejected. Reason: {reason}",
                )
