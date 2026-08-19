from odoo import fields, models


class FastFinancialMonthlySummary(models.Model):
    _name = "fast.financial.monthly.summary"
    _description = "Fast Financial Monthly Summary"
    _order = "month_start desc, account_id, scope, analytic_account_id"
    _rec_name = "month_start"

    month_start = fields.Date(required=True, index=True)
    company_id = fields.Many2one(
        "res.company", required=True, index=True, ondelete="cascade",
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id",
        store=True, readonly=True,
    )
    account_id = fields.Many2one(
        "account.account", required=True, index=True, ondelete="cascade",
    )
    scope = fields.Selection(
        [
            ("total", "Consolidated Total"),
            ("none", "Without Analytic"),
            ("analytic", "Analytic Account"),
        ],
        required=True, default="total", index=True, readonly=True,
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account", index=True, ondelete="set null", readonly=True,
    )
    analytic_key = fields.Char(required=True, default="TOTAL", index=True, readonly=True)
    debit = fields.Monetary(currency_field="currency_id", readonly=True)
    credit = fields.Monetary(currency_field="currency_id", readonly=True)
    balance = fields.Monetary(currency_field="currency_id", readonly=True)
    source_line_count = fields.Integer(readonly=True)

    _sql_constraints = [
        (
            "fast_fin_monthly_unique",
            "unique(month_start, company_id, account_id, analytic_key)",
            "A monthly summary already exists for this month, company, account and analytic key.",
        ),
    ]
