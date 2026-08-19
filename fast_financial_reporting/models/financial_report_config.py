from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FastFinancialReportConfig(models.Model):
    _name = "fast.financial.report.config"
    _description = "Fast Financial Reporting Configuration"

    name = fields.Char(required=True, default="Default")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", required=True,
        default=lambda self: self.env.company, ondelete="cascade",
    )
    posted_only = fields.Boolean(default=True, readonly=True)
    daily_summary_enabled = fields.Boolean(default=True)
    monthly_summary_enabled = fields.Boolean(default=True)
    days_per_cron = fields.Integer(
        string="Days per Cron Run",
        default=1,
        help="Start with 1 on staging. Allowed range: 1-7.",
    )
    notes = fields.Text()

    _sql_constraints = [
        (
            "fast_fin_config_company_name_unique",
            "unique(company_id, name)",
            "The configuration name must be unique per company.",
        ),
    ]

    @api.constrains("days_per_cron")
    def _check_days_per_cron(self):
        for rec in self:
            if not 1 <= rec.days_per_cron <= 7:
                raise ValidationError("Days per Cron Run must be between 1 and 7.")

    @api.model
    def get_for_company(self, company):
        rec = self.search([
            ("company_id", "=", company.id),
            ("active", "=", True),
        ], limit=1)
        if not rec:
            rec = self.create({"company_id": company.id, "name": "Default"})
        return rec
