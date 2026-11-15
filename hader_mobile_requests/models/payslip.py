from datetime import date

from odoo import _, api, fields, models


class HaderMobilePayslip(models.Model):
    _name = "hader.mobile.payslip"
    _description = "Employee Monthly Payslip (قسيمة راتب شهرية)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"

    name = fields.Char(
        string="رقم قسيمة الراتب / Reference",
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
        ondelete="cascade",
        tracking=True,
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
    month_label = fields.Char(
        string="الشهر / الفترة (Month / Period)",
        required=True,
        default=lambda self: fields.Date.context_today(self).strftime("%Y-%m"),
        tracking=True,
    )
    date_from = fields.Date(
        string="من تاريخ / Date From",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
        tracking=True,
    )
    date_to = fields.Date(
        string="إلى تاريخ / Date To",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    payment_date = fields.Date(
        string="تاريخ الصرف / Payment Date",
        default=fields.Date.context_today,
        tracking=True,
    )
    basic_wage = fields.Monetary(
        string="الراتب الأساسي / Basic Salary",
        currency_field="currency_id",
        required=True,
        default=0.0,
        tracking=True,
    )
    housing_allowance = fields.Monetary(
        string="بدل السكن / Housing Allowance",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    transport_allowance = fields.Monetary(
        string="بدل المواصلات / Transport Allowance",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    other_allowance = fields.Monetary(
        string="بدلات ومكافآت أخرى / Other Allowances & Bonus",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    deductions = fields.Monetary(
        string="الخصومات والاستقطاعات / Deductions",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    loan_deduction = fields.Monetary(
        string="استقطاع السلف / Loan Installment Deduction",
        currency_field="currency_id",
        default=0.0,
        tracking=True,
    )
    gross_wage = fields.Monetary(
        string="إجمالي الاستحقاقات / Gross Salary",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    total_deductions = fields.Monetary(
        string="إجمالي الاستقطاعات / Total Deductions",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    net_wage = fields.Monetary(
        string="صافي الراتب المستحق / Net Salary",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    state = fields.Selection(
        [
            ("draft", "مسودة / Draft"),
            ("confirmed", "معتمد / Confirmed"),
            ("paid", "تم الصرف / Paid"),
        ],
        string="الحالة / Status",
        default="confirmed",
        required=True,
        tracking=True,
    )
    notes = fields.Text(string="ملاحظات / Notes")
    active = fields.Boolean(default=True)

    @api.depends(
        "basic_wage",
        "housing_allowance",
        "transport_allowance",
        "other_allowance",
        "deductions",
        "loan_deduction",
    )
    def _compute_totals(self):
        for rec in self:
            gross = (
                (rec.basic_wage or 0.0)
                + (rec.housing_allowance or 0.0)
                + (rec.transport_allowance or 0.0)
                + (rec.other_allowance or 0.0)
            )
            ded = (rec.deductions or 0.0) + (rec.loan_deduction or 0.0)
            rec.gross_wage = gross
            rec.total_deductions = ded
            rec.net_wage = max(0.0, gross - ded)

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id:
            emp = self.employee_id
            if "hr.contract" in self.env:
                contract = self.env["hr.contract"].sudo().search(
                    [("employee_id", "=", emp.id), ("state", "in", ["open", "draft"])],
                    order="date_start desc, id desc",
                    limit=1,
                )
                if contract and contract.wage:
                    self.basic_wage = contract.wage
            elif "wage" in emp._fields and emp.wage:
                self.basic_wage = emp.wage

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                today_str = fields.Date.context_today(self).strftime("%Y%m")
                count = self.sudo().search_count([]) + 1
                vals["name"] = f"SLIP/{today_str}/{count:04d}"
        return super().create(vals_list)

    def action_confirm(self):
        self.write({"state": "confirmed"})
        if "hader.mobile.notification.inbox" in self.env:
            for rec in self:
                self.env["hader.mobile.notification.inbox"].notify_employee(
                    rec.employee_id,
                    "قسيمة راتب جديدة",
                    f"تم إصدار واعتماد قسيمة راتب شهر ({rec.month_label}) بصافي {rec.net_wage:.2f}.",
                    "payslip_issued",
                    title_en="New Payslip Available",
                    body_en=f"Your payslip for ({rec.month_label}) has been issued with net salary {rec.net_wage:.2f}.",
                )

    def action_mark_paid(self):
        self.write({"state": "paid", "payment_date": fields.Date.context_today(self)})
        if "hader.mobile.notification.inbox" in self.env:
            for rec in self:
                self.env["hader.mobile.notification.inbox"].notify_employee(
                    rec.employee_id,
                    "تم صرف الراتب",
                    f"تم تحويل وصرف راتب شهر ({rec.month_label}) بصافي {rec.net_wage:.2f}.",
                    "payslip_paid",
                    title_en="Salary Paid",
                    body_en=f"Your salary for ({rec.month_label}) of {rec.net_wage:.2f} has been marked as paid.",
                )

    def mobile_dto(self, locale="ar"):
        self.ensure_one()
        is_ar = (locale or "ar").startswith("ar")
        currency = self.currency_id.name if self.currency_id else "SAR"
        state_label = {
            "draft": "مسودة" if is_ar else "Draft",
            "confirmed": "معتمد" if is_ar else "Confirmed",
            "paid": "تم الصرف" if is_ar else "Paid",
        }.get(self.state, self.state)
        return {
            "id": self.id,
            "reference": self.name or "",
            "month_label": self.month_label or "",
            "date_from": self.date_from.isoformat() if self.date_from else "",
            "date_to": self.date_to.isoformat() if self.date_to else "",
            "payment_date": self.payment_date.isoformat() if self.payment_date else "",
            "currency": currency,
            "basic_wage": float(self.basic_wage or 0.0),
            "housing_allowance": float(self.housing_allowance or 0.0),
            "transport_allowance": float(self.transport_allowance or 0.0),
            "other_allowance": float(self.other_allowance or 0.0),
            "deductions": float(self.deductions or 0.0),
            "loan_deduction": float(self.loan_deduction or 0.0),
            "gross_wage": float(self.gross_wage or 0.0),
            "total_deductions": float(self.total_deductions or 0.0),
            "net_wage": float(self.net_wage or 0.0),
            "state": self.state,
            "state_label": state_label,
            "notes": self.notes or "",
        }
