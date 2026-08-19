from odoo import fields, models

class FastFinancialReportConfig(models.Model):
    _name = "fast.financial.report.config"
    _description = "Fast Financial Reporting Configuration"

    name = fields.Char(required=True, default="Default")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade")
    posted_only = fields.Boolean(default=True, readonly=True, help="Version 1 is intentionally limited to posted entries.")
    daily_summary_enabled = fields.Boolean(default=True)
    monthly_summary_enabled = fields.Boolean(default=True)
    notes = fields.Text()

    _sql_constraints = [("fast_fin_config_company_name_unique", "unique(company_id, name)", "The configuration name must be unique per company.")]
