from odoo import fields, models


class FastFinancialDailySummary(models.Model):
    _name = "fast.financial.daily.summary"
    _description = "Fast Financial Daily Summary"
    _order = "date desc, account_id, scope, analytic_account_id"
    _rec_name = "date"

    date = fields.Date(required=True, index=True)
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
    analytic_key = fields.Char(
        required=True, default="TOTAL", index=True, readonly=True,
        help="TOTAL, NONE, or AA:<analytic_account_id>.",
    )
    debit = fields.Monetary(currency_field="currency_id", readonly=True)
    credit = fields.Monetary(currency_field="currency_id", readonly=True)
    balance = fields.Monetary(currency_field="currency_id", readonly=True)
    source_line_count = fields.Integer(readonly=True)

    _sql_constraints = [
        (
            "fast_fin_daily_unique",
            "unique(date, company_id, account_id, analytic_key)",
            "A daily summary already exists for this date, company, account and analytic key.",
        ),
    ]
