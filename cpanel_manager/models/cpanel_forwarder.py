from odoo import fields, models


class CpanelForwarder(models.Model):
    _name = "cpanel.forwarder"
    _description = "cPanel Email Forwarder"
    _order = "source, destination"

    source = fields.Char(required=True, index=True)
    destination = fields.Char(required=True, index=True)
    server_id = fields.Many2one("cpanel.server", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="server_id.company_id", store=True, index=True)
    remote_exists = fields.Boolean(default=True, readonly=True)
    last_sync = fields.Datetime(readonly=True)

    _sql_constraints = [
        ("server_route_unique", "unique(server_id, source, destination)", "This forwarder already exists."),
    ]
