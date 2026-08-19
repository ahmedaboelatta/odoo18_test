from odoo import fields, models

class FastFinancialSyncState(models.Model):
    _name = "fast.financial.sync.state"
    _description = "Fast Financial Reporting Sync State"
    _order = "id desc"

    name = fields.Char(required=True, default="Main Reporting Engine")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade")
    state = fields.Selection([("not_initialized", "Not Initialized"), ("ready", "Ready"), ("running", "Running"), ("error", "Error")], required=True, default="not_initialized", readonly=True)
    last_sync_at = fields.Datetime(readonly=True)
    last_source_write_date = fields.Datetime(readonly=True)
    last_source_id = fields.Integer(readonly=True)
    last_rebuild_from = fields.Date(readonly=True)
    last_rebuild_to = fields.Date(readonly=True)
    last_error = fields.Text(readonly=True)
    note = fields.Text(help="Administrative notes. No synchronization is performed in version 0.1.")

    _sql_constraints = [("fast_fin_sync_company_unique", "unique(company_id)", "Only one Fast Financial Reporting sync state is allowed per company.")]
