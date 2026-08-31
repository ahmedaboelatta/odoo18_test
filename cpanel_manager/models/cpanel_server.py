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
    forwarder_ids = fields.One2many("cpanel.forwarder", "server_id")
    mailbox_count = fields.Integer(compute="_compute_counts")
    domain_count = fields.Integer(compute="_compute_counts")
    restricted_mailbox_count = fields.Integer(compute="_compute_counts")
    unlimited_mailbox_count = fields.Integer(compute="_compute_counts")
    over_quota_mailbox_count = fields.Integer(compute="_compute_counts")
    forwarder_count = fields.Integer(compute="_compute_counts")
    # Store hosting capacity in GB. These are deliberately new column names so
    # upgrades from the original byte/integer fields cannot retain an int4 type.
    disk_used_gb = fields.Float(readonly=True, digits=(16, 2))
    disk_limit_gb = fields.Float(readonly=True, digits=(16, 2))
    disk_usage_percent = fields.Float(compute="_compute_disk_percent")
    last_sync = fields.Datetime(readonly=True)
    last_status = fields.Selection([("unknown", "Unknown"), ("ok", "Connected"), ("error", "Error")], default="unknown", readonly=True, tracking=True)
    last_error = fields.Text(readonly=True)
    warning_percent = fields.Float(default=85.0, required=True)
    database_usage = fields.Char(readonly=True)
    file_usage = fields.Char(readonly=True)
    bandwidth_usage = fields.Char(readonly=True)
    addon_domain_usage = fields.Char(readonly=True)
    subdomain_usage = fields.Char(readonly=True)
    alias_domain_usage = fields.Char(readonly=True)
    email_account_usage = fields.Char(readonly=True)
    forwarder_usage = fields.Char(readonly=True)
    mailing_list_usage = fields.Char(readonly=True)
    autoresponder_usage = fields.Char(readonly=True)
    email_filter_usage = fields.Char(readonly=True)
    ftp_account_usage = fields.Char(readonly=True)
    postgresql_database_usage = fields.Char(readonly=True)

    _sql_constraints = [("host_user_unique", "unique(host, username, company_id)", "This cPanel account is already configured.")]

    @api.constrains("host")
    def _check_host(self):
        for record in self:
            value = (record.host or "").strip()
            if "://" in value or "/" in value:
                raise ValidationError(_("Enter the hostname only, without protocol, port, or path."))

    @api.depends(
        "mailbox_ids",
        "mailbox_ids.is_restricted",
        "mailbox_ids.is_unlimited",
        "mailbox_ids.is_over_quota",
        "domain_ids",
        "forwarder_ids",
        "forwarder_ids.remote_exists",
    )
    def _compute_counts(self):
        for record in self:
            record.mailbox_count = len(record.mailbox_ids)
            record.domain_count = len(record.domain_ids)
            record.restricted_mailbox_count = len(record.mailbox_ids.filtered("is_restricted"))
            record.unlimited_mailbox_count = len(record.mailbox_ids.filtered("is_unlimited"))
            record.over_quota_mailbox_count = len(record.mailbox_ids.filtered("is_over_quota"))
            record.forwarder_count = len(record.forwarder_ids.filtered("remote_exists"))

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
            # Some providers return the UAPI result object directly. Do not
            # inspect that same dictionary twice or the user sees duplicate
            # error and warning messages.
            sources = [result]
            if payload is not result:
                sources.append(payload)
            for source in sources:
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

    @staticmethod
    def _float_number(value):
        try:
            return float(str(value or 0).replace(",", "").strip())
        except (TypeError, ValueError):
            return 0.0

    def action_sync(self):
        for record in self:
            try:
                record._sync_mailboxes()
                record._sync_domains()
                record._sync_forwarders()
                record._sync_usage()
                record._sync_statistics()
                record.write({"last_sync": fields.Datetime.now(), "last_status": "ok", "last_error": False})
                # A notification failure must never roll back synchronized
                # cPanel data. Keep this optional step in its own savepoint.
                try:
                    with self.env.cr.savepoint():
                        record._create_capacity_activities()
                except Exception:
                    _logger.exception("Could not create cPanel capacity activity for %s", record.display_name)
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
        rows = self._api_call("Email", "list_pops_with_disk", {"get_restrictions": 1, "skip_main": 0}) or []
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
                "is_system_account": bool(
                    self._number(row.get("is_main_account") or row.get("is_system_account"))
                    or row.get("type") in ("main", "system")
                ),
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

    def _sync_forwarders(self):
        rows = []
        # UAPI requires a domain, unlike the legacy API2 call. Query every
        # synchronized domain and merge the routes into one Odoo list.
        for domain in self.domain_ids.filtered("remote_exists"):
            domain_rows = self._api_call("Email", "list_forwarders", {"domain": domain.name}) or []
            if isinstance(domain_rows, dict):
                domain_rows = domain_rows.get("forwarders") or domain_rows.get("items") or [domain_rows]
            rows.extend(domain_rows)
        seen = set()
        model = self.env["cpanel.forwarder"].sudo()
        for row in rows:
            if not isinstance(row, dict):
                continue
            # Email::list_forwarders uses the slightly confusing ``dest`` for
            # the address that receives mail and ``forward`` for its target.
            source = row.get("email") or row.get("dest") or row.get("source")
            destination = row.get("forward") or row.get("destination")
            if not source or not destination:
                continue
            key = (str(source).lower(), str(destination).lower())
            seen.add(key)
            vals = {
                "server_id": self.id,
                "source": key[0],
                "destination": key[1],
                "remote_exists": True,
                "last_sync": fields.Datetime.now(),
            }
            existing = model.search([
                ("server_id", "=", self.id),
                ("source", "=", key[0]),
                ("destination", "=", key[1]),
            ], limit=1)
            if not existing:
                # Repair records created by older module versions where the
                # two cPanel response fields were interpreted in reverse.
                existing = model.search([
                    ("server_id", "=", self.id),
                    ("source", "=", key[1]),
                    ("destination", "=", key[0]),
                ], limit=1)
            existing.write(vals) if existing else model.create(vals)
        for forwarder in model.search([("server_id", "=", self.id)]):
            if (forwarder.source, forwarder.destination) not in seen:
                forwarder.remote_exists = False

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

    @staticmethod
    def _format_stat(item):
        if not isinstance(item, dict):
            return "—"
        count = item.get("count", item.get("_count", item.get("value", item.get("usage", 0))))
        maximum = item.get("max", item.get("_max", item.get("maximum", item.get("limit", "unlimited"))))
        units = item.get("units") or item.get("unit") or ""
        unlimited_values = (None, "", 0, "0", "unlimited", "∞")
        maximum = "∞" if maximum in unlimited_values else maximum
        count_text = "%s %s" % (count, units) if units else str(count)
        maximum_text = "%s %s" % (maximum, units) if units and maximum != "∞" else str(maximum)
        return "%s / %s" % (count_text.strip(), maximum_text.strip())

    def _sync_statistics(self):
        display = "diskusage|mysqldatabases|sqldatabases|fileusage|bandwidthusage|addondomains|subdomains|parkeddomains|emailaccounts|mailinglists|autoresponders|emailforwarders|emailfilters|ftpaccounts|postgresqldatabases"
        rows = self._api_call("StatsBar", "get_stats", {"display": display}) or []
        if isinstance(rows, dict):
            nested = rows.get("items") or rows.get("stats")
            if isinstance(nested, list):
                rows = nested
            elif rows and all(isinstance(value, dict) for value in rows.values()):
                rows = [dict(value, id=value.get("id") or key) for key, value in rows.items()]
            else:
                rows = [rows]
        stats = {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            key = "".join(
                character
                for character in str(item.get("id") or item.get("name") or item.get("langkey") or "").lower()
                if character.isalnum()
            )
            stats[key] = item

        disk = stats.get("diskusage")
        if disk and not self.disk_used_gb:
            unit = str(disk.get("units") or disk.get("unit") or "MB").upper()
            factor = {"B": 1 / 1073741824.0, "KB": 1 / 1048576.0, "MB": 1 / 1024.0, "GB": 1.0, "TB": 1024.0}.get(unit, 1 / 1024.0)
            used = self._float_number(disk.get("count", disk.get("_count", 0))) * factor
            maximum_raw = disk.get("max", disk.get("_max", 0))
            maximum = self._float_number(maximum_raw) * factor
            self.write({"disk_used_gb": used, "disk_limit_gb": maximum})

        def find(*names):
            for name in names:
                if name in stats:
                    return self._format_stat(stats[name])
            return _("Not available")

        self.write({
            "database_usage": find("databases", "mysqldatabases", "sqldatabases"),
            "file_usage": find("fileusage"),
            "bandwidth_usage": find("bandwidthusage"),
            "addon_domain_usage": find("addondomains"),
            "subdomain_usage": find("subdomains"),
            "alias_domain_usage": find("parkeddomains", "aliasdomains"),
            "email_account_usage": find("emailaccounts"),
            "forwarder_usage": find("emailforwarders", "forwarders"),
            "mailing_list_usage": find("mailinglists"),
            "autoresponder_usage": find("autoresponders"),
            "email_filter_usage": find("emailfilters"),
            "ftp_account_usage": find("ftpaccounts"),
            "postgresql_database_usage": find("postgresqldatabases"),
        })
        # These values are authoritative from the synchronized records even if
        # a hosting provider hides the corresponding StatsBar item.
        self.write({
            "email_account_usage": "%s / ∞" % len(self.mailbox_ids.filtered("remote_exists")),
            "forwarder_usage": "%s / ∞" % len(self.forwarder_ids.filtered("remote_exists")),
        })

    def _create_capacity_activities(self):
        for record in self:
            if record.disk_limit_gb and record.disk_usage_percent >= record.warning_percent:
                existing = self.env["mail.activity"].search([("res_model", "=", record._name), ("res_id", "=", record.id), ("summary", "=", "cPanel storage warning")], limit=1)
                if not existing:
                    record.activity_schedule(
                        "mail.mail_activity_data_warning",
                        summary="cPanel storage warning",
                        note=_("Hosting storage usage reached %.1f%%.") % record.disk_usage_percent,
                    )
            for mailbox in record.mailbox_ids.filtered(
                lambda item: item.remote_exists
                and item.quota_mb
                and item.usage_percent >= record.warning_percent
            ):
                summary = "Mailbox storage warning: %s" % mailbox.name
                existing = self.env["mail.activity"].search([
                    ("res_model", "=", record._name),
                    ("res_id", "=", record.id),
                    ("summary", "=", summary),
                ], limit=1)
                if not existing:
                    record.activity_schedule(
                        "mail.mail_activity_data_warning",
                        summary=summary,
                        note=_("Mailbox %s has reached %.1f%% of its quota (%s).")
                        % (mailbox.name, mailbox.usage_percent, mailbox.quota_display),
                    )

    def _log(self, operation, success, message, mailbox=None):
        self.env["cpanel.operation.log"].sudo().create({"server_id": self.id, "mailbox_id": mailbox and mailbox.id, "operation": operation, "success": success, "message": message})

    @api.model
    def _cron_sync(self):
        for server in self.search([("active", "=", True)]):
            try:
                server.action_sync()
            except Exception:
                _logger.exception("Scheduled cPanel sync failed for %s", server.display_name)
