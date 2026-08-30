from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    spf_status = fields.Selection(
        [("unknown", "Unknown"), ("valid", "Valid"), ("invalid", "Needs Attention"), ("error", "Error")],
        default="unknown", readonly=True, index=True,
    )
    dkim_status = fields.Selection(
        [("unknown", "Unknown"), ("valid", "Valid"), ("invalid", "Needs Attention"), ("error", "Error")],
        default="unknown", readonly=True, index=True,
    )
    dmarc_status = fields.Selection(
        [("unknown", "Unknown"), ("valid", "Valid"), ("invalid", "Needs Attention"), ("error", "Error")],
        default="unknown", readonly=True, index=True,
    )
    dns_health = fields.Selection(
        [("unknown", "Unknown"), ("healthy", "Healthy"), ("warning", "Needs Attention"), ("error", "Error")],
        compute="_compute_dns_health", store=True, index=True,
    )
    dns_health_details = fields.Text(readonly=True)
    dns_last_check = fields.Datetime(readonly=True)

    _sql_constraints = [("server_domain_unique", "unique(server_id, name)", "This domain already exists on this server.")]

    @api.depends("remote_exists")
    def _compute_status(self):
        for record in self:
            record.status = "active" if record.remote_exists else "missing"

    @api.depends("spf_status", "dkim_status", "dmarc_status")
    def _compute_dns_health(self):
        for record in self:
            values = {record.spf_status, record.dkim_status, record.dmarc_status}
            if "error" in values:
                record.dns_health = "error"
            elif "invalid" in values:
                record.dns_health = "warning"
            elif values == {"valid"}:
                record.dns_health = "healthy"
            else:
                record.dns_health = "unknown"

    @staticmethod
    def _validation_status(data):
        found_valid = False

        def walk(value):
            if isinstance(value, dict):
                yield value
                for nested in value.values():
                    yield from walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    yield from walk(nested)

        for row in walk(data):
            for key in ("valid", "is_valid", "validity"):
                if key in row:
                    valid = bool(row[key]) and str(row[key]).lower() not in ("0", "false", "invalid")
                    if not valid:
                        return "invalid"
                    found_valid = True
            state = str(row.get("state") or row.get("status") or row.get("result") or "").lower()
            if state in ("valid", "ok", "pass", "passed", "1", "true"):
                found_valid = True
            if state in ("invalid", "fail", "failed", "0", "false", "missing"):
                return "invalid"
        return "valid" if found_valid else "unknown"

    def action_check_dns_health(self):
        functions = {
            "spf_status": "validate_current_spfs",
            "dkim_status": "validate_current_dkims",
            "dmarc_status": "validate_current_dmarcs",
        }
        for record in self:
            values = {"dns_last_check": fields.Datetime.now()}
            details = []
            for field_name, function in functions.items():
                try:
                    data = record.server_id._api_call("EmailAuth", function, {"domain": record.name})
                    values[field_name] = record._validation_status(data)
                    if values[field_name] == "unknown":
                        details.append(_("%s returned no recognizable validation state.") % field_name.replace("_status", "").upper())
                except UserError as exc:
                    values[field_name] = "error"
                    details.append("%s: %s" % (field_name.replace("_status", "").upper(), exc))
            values["dns_health_details"] = "\n".join(details) or False
            record.write(values)
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Email DNS Health"), "message": _("DNS checks completed."), "type": "success", "next": {"type": "ir.actions.client", "tag": "reload"}},
        }
