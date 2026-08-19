from odoo import api, fields, models


class FastFinancialSyncState(models.Model):
    _name = "fast.financial.sync.state"
    _description = "Fast Financial Reporting Sync State"
    _order = "id desc"

    name = fields.Char(required=True, default="Main Reporting Engine")
    company_id = fields.Many2one(
        "res.company", required=True,
        default=lambda self: self.env.company, ondelete="cascade",
    )
    state = fields.Selection(
        [
            ("not_initialized", "Not Initialized"),
            ("ready", "Ready"),
            ("running", "Running"),
            ("error", "Error"),
        ],
        required=True, default="not_initialized", readonly=True,
    )
    last_sync_at = fields.Datetime(readonly=True)
    last_rebuild_from = fields.Date(readonly=True)
    last_rebuild_to = fields.Date(readonly=True)
    last_error = fields.Text(readonly=True)
    note = fields.Text()

    _sql_constraints = [
        (
            "fast_fin_sync_company_unique",
            "unique(company_id)",
            "Only one sync state is allowed per company.",
        ),
    ]

    @api.model
    def get_or_create_for_company(self, company):
        rec = self.search([("company_id", "=", company.id)], limit=1)
        if not rec:
            rec = self.create({"company_id": company.id})
        return rec
