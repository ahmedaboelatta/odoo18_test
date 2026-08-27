import json
import logging
import ssl
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CpanelServer(models.Model):
    _name = "cpanel.server"
    _description = "cPanel Server"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    host = fields.Char(required=True, help="Hostname only, for example server.example.com")
    port = fields.Integer(default=2083, required=True)
    username = fields.Char(required=True)
    api_token = fields.Char(required=True, groups="cpanel_manager.group_cpanel_admin")
    verify_ssl = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    mailbox_ids = fields.One2many("cpanel.mailbox", "server_id")
    domain_ids = fields.One2many("cpanel.domain", "server_id")
    mailbox_count = fields.Integer(compute="_compute_counts")
    domain_count = fields.Integer(compute="_compute_counts")
    # Store hosting capacity in GB. These are deliberately new column names so
    # upgrades from the original byte/integer fields cannot retain an int4 type.
    disk_used_gb = fields.Float(readonly=True, digits=(16, 2))
    disk_limit_gb = fields.Float(readonly=True, digits=(16, 2))
    disk_usage_percent = fields.Float(compute="_compute_disk_percent")
    last_sync = fields.Datetime(readonly=True)
    last_status = fields.Selection([("unknown", "Unknown"), ("ok", "Connected"), ("error", "Error")], default="unknown", readonly=True, tracking=True)
    last_error = fields.Text(readonly=True)
    warning_percent = fields.Float(default=85.0, required=True)

    _sql_constraints = [("host_user_unique", "unique(host, username, company_id)", "This cPanel account is already configured.")]

    @api.constrains("host")
    def _check_host(self):
        for record in self:
            value = (record.host or "").strip()
            if "://" in value or "/" in value:
                raise ValidationError(_("Enter the hostname only, without protocol, port, or path."))

    @api.depends("mailbox_ids", "domain_ids")
    def _compute_counts(self):
        for record in self:
            record.mailbox_count = len(record.mailbox_ids)
            record.domain_count = len(record.domain_ids)

    @api.depends("disk_used_gb", "disk_limit_gb")
    def _compute_disk_percent(self):
        for record in self:
            record.disk_usage_percent = record.disk_limit_gb and (100.0 * record.disk_used_gb / record.disk_limit_gb) or 0.0

    def _api_call(self, module, function, params=None):
        self.ensure_one()
        if not self.api_token:
            raise UserError(_("Set the cPanel API token first."))
        url = "https://%s:%s/execute/%s/%s" % (self.host.strip(), self.port, module, function)
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={"Authorization": "cpanel %s:%s" % (self.username, self.api_token), "Accept": "application/json"})
        # Do not name this variable ``context``: Odoo's translation helper
        # inspects that conventional local name and expects an Odoo context dict.
        ssl_context = ssl.create_default_context() if self.verify_ssl else ssl._create_unverified_context()
        try:
            with urlopen(request, timeout=30, context=ssl_context) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise UserError(_("cPanel connection failed: %s") % exc) from exc
        # Standard cPanel installations wrap UAPI output in ``result``.
        # Some providers (including Bluehost) return that same object directly.
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        if not result.get("status"):
            details = []
            for source in (result, payload):
                for key in ("errors", "messages", "warnings"):
                    value = source.get(key)
                    if not value:
                        continue
                    details.extend(value if isinstance(value, list) else [value])
            metadata = result.get("metadata")
            if metadata and not details:
                details.append(metadata)
            if not details:
                # Keep the response useful for diagnostics without ever logging
                # the request headers (which contain the API token).
                safe_payload = {
                    key: value
                    for key, value in payload.items()
                    if key not in ("headers", "authorization", "api_token")
                }
                details.append(_("Unexpected cPanel response: %s") % json.dumps(safe_payload, ensure_ascii=False))
            raise UserError("\n".join(str(item) for item in details))
        return result.get("data")

    def action_test_connection(self):
        for record in self:
            try:
                record._api_call("Variables", "get_user_information", {"name": "user"})
                record.write({"last_status": "ok", "last_error": False})
            except UserError as exc:
                record.write({"last_status": "error", "last_error": str(exc)})
                raise
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("cPanel"),
                "message": _("Connection succeeded."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    @staticmethod
    def _number(value):
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    def action_sync(self):
        for record in self:
            try:
                record._sync_mailboxes()
                record._sync_domains()
                record._sync_usage()
                record.write({"last_sync": fields.Datetime.now(), "last_status": "ok", "last_error": False})
                record._create_capacity_activities()
                record._log("sync", True, _("cPanel data synchronized."))
            except UserError as exc:
                record.write({"last_status": "error", "last_error": str(exc)})
                record._log("sync", False, str(exc))
                raise
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("cPanel"),
                "message": _("Synchronization completed."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def _sync_mailboxes(self):
        rows = self._api_call("Email", "list_pops_with_disk", {"get_restrictions": 1, "skip_main": 1}) or []
        seen = set()
        model = self.env["cpanel.mailbox"].sudo()
        for row in rows:
            address = row.get("email") or row.get("email_account") or row.get("user")
            domain = row.get("domain")
            if address and "@" not in address and domain:
                address = "%s@%s" % (address, domain)
            if not address or "@" not in address:
                continue
            seen.add(address.lower())
            vals = {
                "server_id": self.id, "name": address.lower(), "domain": address.split("@", 1)[1].lower(),
                "used_mb": self._number(row.get("_diskused") or row.get("diskused")) / 1048576.0,
                "quota_mb": self._number(row.get("_diskquota") or row.get("diskquota")) / 1048576.0,
                "suspended_login": bool(self._number(row.get("suspended_login"))),
                "suspended_incoming": bool(self._number(row.get("suspended_incoming"))),
                "suspended_outgoing": bool(self._number(row.get("suspended_outgoing"))),
                "remote_exists": True, "last_sync": fields.Datetime.now(),
            }
            existing = model.search([("server_id", "=", self.id), ("name", "=", address.lower())], limit=1)
            existing.write(vals) if existing else model.create(vals)
        model.search([("server_id", "=", self.id), ("name", "not in", list(seen))]).write({"remote_exists": False})

    def _sync_domains(self):
        data = self._api_call("DomainInfo", "domains_data") or {}
        rows = []
        if isinstance(data, dict):
            for key in ("main_domain", "addon_domains", "sub_domains", "parked_domains"):
                value = data.get(key, [])
                rows.extend(value if isinstance(value, list) else ([value] if value else []))
        elif isinstance(data, list):
            rows = data
        seen = set()
        model = self.env["cpanel.domain"].sudo()
        for row in rows:
            row = {"domain": row} if isinstance(row, str) else row
            name = row.get("domain") or row.get("servername")
            if not name:
                continue
            seen.add(name.lower())
            vals = {"server_id": self.id, "name": name.lower(), "document_root": row.get("documentroot") or row.get("document_root"), "domain_type": row.get("domain_type") or row.get("type") or "other", "https_redirect": bool(row.get("is_https_redirecting") or row.get("https_redirect_status")), "remote_exists": True, "last_sync": fields.Datetime.now()}
            existing = model.search([("server_id", "=", self.id), ("name", "=", name.lower())], limit=1)
            existing.write(vals) if existing else model.create(vals)
        model.search([("server_id", "=", self.id), ("name", "not in", list(seen))]).write({"remote_exists": False})

    def _sync_usage(self):
        data = self._api_call("Quota", "get_quota_info") or {}
        if not isinstance(data, dict):
            data = {}
        # Quota::get_quota_info returns MB values and is more reliable across
        # hosting providers than the localized strings from StatsBar.
        used_mb = self._number(
            data.get("megabytes_used")
            or data.get("mb_used")
            or data.get("used_mb")
        )
        limit_mb = self._number(
            data.get("megabyte_limit")
            or data.get("megabytes_limit")
            or data.get("mb_limit")
            or data.get("limit_mb")
        )
        if not used_mb and data.get("bytes_used"):
            used_mb = self._number(data.get("bytes_used")) / 1048576.0
        if not limit_mb and data.get("byte_limit"):
            limit_mb = self._number(data.get("byte_limit")) / 1048576.0
        self.write({"disk_used_gb": used_mb / 1024.0, "disk_limit_gb": limit_mb / 1024.0})

    def _create_capacity_activities(self):
        activity_type = self.env.ref("mail.mail_activity_data_warning")
        for record in self:
            if record.disk_limit_gb and record.disk_usage_percent >= record.warning_percent:
                existing = self.env["mail.activity"].search([("res_model", "=", record._name), ("res_id", "=", record.id), ("summary", "=", "cPanel storage warning")], limit=1)
                if not existing:
                    record.activity_schedule(activity_type.id, summary="cPanel storage warning", note=_("Hosting storage usage reached %.1f%%.") % record.disk_usage_percent)

    def _log(self, operation, success, message, mailbox=None):
        self.env["cpanel.operation.log"].sudo().create({"server_id": self.id, "mailbox_id": mailbox and mailbox.id, "operation": operation, "success": success, "message": message})

    @api.model
    def _cron_sync(self):
        for server in self.search([("active", "=", True)]):
            try:
                server.action_sync()
            except Exception:
                _logger.exception("Scheduled cPanel sync failed for %s", server.display_name)
