from odoo import api, fields, models


class CpanelDomain(models.Model):
    _name = "cpanel.domain"
    _description = "cPanel Domain"
    _order = "name"

    name = fields.Char(required=True, index=True)
    server_id = fields.Many2one("cpanel.server", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="server_id.company_id", store=True, index=True)
    domain_type = fields.Char(readonly=True)
    document_root = fields.Char(readonly=True)
    https_redirect = fields.Boolean(readonly=True)
    remote_exists = fields.Boolean(default=True, readonly=True)
    status = fields.Selection(
        [("active", "Active"), ("missing", "Missing from cPanel")],
        compute="_compute_status",
    )
    last_sync = fields.Datetime(readonly=True)

    _sql_constraints = [("server_domain_unique", "unique(server_id, name)", "This domain already exists on this server.")]

    @api.depends("remote_exists")
    def _compute_status(self):
        for record in self:
            record.status = "active" if record.remote_exists else "missing"
