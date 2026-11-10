from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HaderMobileExpenseCategory(models.Model):
    _name = "hader.mobile.expense.category"
    _description = "Mobile Employee Expense Category"
    _order = "sequence, id"

    name = fields.Char(string="التصنيف / Category Name", compute="_compute_name", store=True, readonly=False)
    name_ar = fields.Char(string="الاسم بالعربية / Arabic Name", required=True)
    name_en = fields.Char(string="الاسم بالإنجليزية / English Name", required=True)
    code = fields.Char(string="الكود / Code", required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", string="الشركة / Company", index=True)

    @api.depends("name_ar", "name_en")
    def _compute_name(self):
        for rec in self:
            if rec.name_ar and rec.name_en:
                rec.name = f"{rec.name_ar} / {rec.name_en}"
            else:
                rec.name = rec.name_ar or rec.name_en or ""

    def label_for_locale(self, locale="ar"):
        self.ensure_one()
        if str(locale or "ar").startswith("en"):
            return self.name_en or self.name_ar or self.name
        return self.name_ar or self.name_en or self.name


class HaderMobileExpense(models.Model):
    _name = "hader.mobile.expense"
    _description = "Employee Mobile Expense Request"
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
    category_id = fields.Many2one(
        "hader.mobile.expense.category",
        string="تصنيف المصروف / Category",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    title = fields.Char(
        string="بيان المصروف / Expense Title",
        required=True,
        tracking=True,
    )
    expense_date = fields.Date(
        string="تاريخ المصروف / Expense Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    amount = fields.Monetary(
        string="المبلغ / Amount",
        currency_field="currency_id",
        required=True,
        tracking=True,
    )
    notes = fields.Text(
        string="التفاصيل والملاحظات / Notes",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("submitted", "بانتظار موافقة المدير / Waiting Manager"),
            ("manager_approved", "معتمد من المدير / Manager Approved"),
            ("approved", "معتمد نهائياً / Approved"),
            ("rejected", "مرفوض / Rejected"),
        ],
        string="الحالة / Status",
        default="submitted",
        required=True,
        tracking=True,
        index=True,
    )
    manager_review_note = fields.Text(
        string="ملاحظة المدير المباشر / Manager Note",
        readonly=True,
        tracking=True,
    )
    manager_reviewed_by_id = fields.Many2one(
        "hr.employee",
        string="تمت مراجعة المدير بواسطة / Reviewed By Manager",
        readonly=True,
        ondelete="set null",
    )
    manager_reviewed_at = fields.Datetime(
        string="تاريخ مراجعة المدير / Manager Reviewed At",
        readonly=True,
    )
    admin_note = fields.Text(
        string="ملاحظة الإدارة / Accounting Note",
        tracking=True,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        compute="_compute_attachments",
        string="المرفقات والفواتير / Attachments",
    )
    attachment_count = fields.Integer(
        compute="_compute_attachments",
        string="عدد المرفقات / Attachments Count",
    )
    active = fields.Boolean(default=True, tracking=True)

    @api.constrains("amount")
    def _check_amount_positive(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("قيمة المصروف يجب أن تكون أكبر من الصفر. / Expense amount must be greater than zero."))

    def _compute_attachments(self):
        Attachment = self.env["ir.attachment"].sudo()
        for rec in self:
            atts = Attachment.search([
                ("res_model", "=", "hader.mobile.expense"),
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
                dt = record.expense_date or fields.Date.context_today(record)
                record.name = f"EXP/{dt.year:04d}/{dt.month:02d}/{record.id:05d}"
        return records

    def mobile_review(self, manager_employee, decision, note=None):
        """Review expense request by designated approver or direct manager from the mobile app."""
        self.ensure_one()
        is_allowed = (
            self.employee_id != manager_employee
            and (
                self.manager_id == manager_employee
                or (
                    hasattr(self.employee_id, "_is_mobile_approver")
                    and self.employee_id._is_mobile_approver(manager_employee, "expense_manager_id")
                )
                or self.employee_id.parent_id == manager_employee
            )
        )
        if not is_allowed:
            raise ValidationError(_("فقط المدير المباشر أو المعتمد للموظف يمكنه مراجعة هذا الطلب. / Only the employee's designated manager/approver can review this expense."))
        if self.state != "submitted":
            raise ValidationError(_("تمت مراجعة هذا الطلب مسبقاً. / This expense request has already been reviewed."))
        if decision not in ("approve", "reject"):
            raise ValidationError(_("قرار المراجعة غير صالح. / Invalid review decision."))
        cleaned_note = (note or "").strip()
        if decision == "reject" and not cleaned_note:
            raise ValidationError(_("سبب الرفض مطلوب. / A rejection reason is required."))

        vals = {
            "state": "manager_approved" if decision == "approve" else "rejected",
            "manager_review_note": cleaned_note or (_("تم الاعتماد من المدير المباشر %s") % manager_employee.name),
            "manager_reviewed_by_id": manager_employee.id,
            "manager_reviewed_at": fields.Datetime.now(),
        }
        self.sudo().write(vals)
        return True

    def action_manager_approve(self):
        for rec in self:
            if rec.state != "submitted":
                continue
            reviewer_emp = self.env.user.employee_id or rec.manager_id
            rec.write({
                "state": "manager_approved",
                "manager_reviewed_by_id": reviewer_emp.id if reviewer_emp else False,
                "manager_reviewed_at": fields.Datetime.now(),
                "manager_review_note": rec.manager_review_note or (_("Approved by %s") % self.env.user.name),
            })

    def action_approve(self):
        Inbox = self.env["hader.mobile.notification.inbox"].sudo() if "hader.mobile.notification.inbox" in self.env else False
        for rec in self:
            if rec.state == "approved":
                continue
            vals = {"state": "approved"}
            if not rec.manager_reviewed_at:
                vals["manager_reviewed_at"] = fields.Datetime.now()
            rec.write(vals)
            if Inbox and rec.employee_id:
                Inbox.notify_employee(
                    rec.employee_id,
                    "تم الاعتماد النهائي لطلب المصاريف",
                    f"تم اعتماد طلب المصاريف الخاص بك ({rec.name} - {rec.title}) بمبلغ {rec.amount:.2f}.",
                    "expense_result",
                    title_en="Expense request approved",
                    body_en=f"Your expense request ({rec.name} - {rec.title}) for {rec.amount:.2f} has been finally approved.",
                )

    def action_reject(self):
        Inbox = self.env["hader.mobile.notification.inbox"].sudo() if "hader.mobile.notification.inbox" in self.env else False
        for rec in self:
            reason = (rec.admin_note or rec.manager_review_note or "").strip()
            if not reason:
                raise ValidationError(_("يرجى كتابة سبب الرفض في حقل (ملاحظة الإدارة) قبل رفض الطلب. / Please enter a rejection reason in Accounting Note before rejecting."))
            rec.write({"state": "rejected"})
            if Inbox and rec.employee_id:
                Inbox.notify_employee(
                    rec.employee_id,
                    "تم رفض طلب المصاريف",
                    f"تم رفض طلب المصاريف ({rec.name} - {rec.title}). السبب: {reason}",
                    "expense_result",
                    title_en="Expense request rejected",
                    body_en=f"Your expense request ({rec.name} - {rec.title}) was rejected. Reason: {reason}",
                )
