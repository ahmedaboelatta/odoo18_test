from odoo import _, fields, models
from odoo.exceptions import UserError


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

    def action_delete_remote(self):
        for record in self:
            if not record.remote_exists:
                raise UserError(_("This forwarder no longer exists in cPanel."))
            try:
                record.server_id._api_call(
                    "Email",
                    "delete_forwarder",
                    {"email": record.source, "emaildest": record.destination},
                )
                record.server_id._log(
                    "delete_forwarder",
                    True,
                    _("Deleted forwarder %s to %s") % (record.source, record.destination),
                )
            except UserError as exc:
                record.server_id._log("delete_forwarder", False, str(exc))
                raise
        for server in self.mapped("server_id"):
            server._sync_forwarders()
        return True

    def action_edit(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Edit Forwarder"),
            "res_model": "cpanel.forwarder.create.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_forwarder_id": self.id},
        }
