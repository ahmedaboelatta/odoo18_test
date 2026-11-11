import base64
import json
import logging
import urllib.request

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)
DEFAULT_MASTER_SECRET = "HADER-SAAS-MASTER-2026-SECRET"


class HaderMobileSubscriptionSync(models.Model):
    _inherit = "hader.mobile.subscription"

    def _extract_logo_base64(self):
        self.ensure_one()
        logo = self.logo
        if not logo and self.company_id:
            branding = self.env["hader.mobile.branding"].sudo().search(
                [("company_id", "=", self.company_id.id), ("active", "=", True)], limit=1
            )
            if branding and branding.logo:
                logo = branding.logo
            elif self.company_id.logo:
                logo = self.company_id.logo
        if hasattr(logo, "content"):
            return base64.b64encode(logo.content).decode("ascii") if logo.content else None
        if isinstance(logo, bytes):
            return logo.decode("ascii")
        return logo or None

    def _sync_to_client_server(self, log_chatter=False):
        secret = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hader_mobile.master_secret", DEFAULT_MASTER_SECRET)
        )
        for record in self:
            if record.hosting_type == "cloud_shared":
                record.apply_features_to_local_flags()
            target_url = (record.server_url or "").strip().rstrip("/")
            if not target_url or target_url.endswith("/odoo20"):
                continue
            sync_endpoint = f"{target_url}/hader/api/v1/license/sync"
            payload = {
                "company_code": record.company_code,
                "name": record.name,
                "name_en": record.name_en or record.name,
                "logo_base64": record._extract_logo_base64(),
                "hosting_type": record.hosting_type,
                "odoo_version": record.odoo_version,
                "server_url": target_url,
                "db_name": record.db_name or None,
                "plan_type": record.plan_type,
                "state": record.state,
                "start_date": record.start_date.isoformat() if record.start_date else None,
                "end_date": record.end_date.isoformat() if record.end_date else None,
                "max_employees": record.max_employees,
                "feature_attendance": bool(record.feature_attendance),
                "feature_leaves": bool(record.feature_leaves),
                "feature_expenses": bool(record.feature_expenses),
                "feature_services": bool(record.feature_services),
                "feature_payroll": bool(record.feature_payroll),
                "feature_notifications": bool(record.feature_notifications),
                "feature_calendar": bool(record.feature_calendar),
                "feature_custody": bool(record.feature_custody),
                "feature_tasks": bool(record.feature_tasks),
                "feature_team_attendance": bool(record.feature_team_attendance),
                "feature_directory": bool(record.feature_directory),
                "license_key": record.license_key,
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Hader-Master-Secret": secret,
            }
            if record.db_name:
                headers["X-Odoo-Database"] = record.db_name
            try:
                req = urllib.request.Request(
                    sync_endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    data = body.get("data") or {}
                    remote_count = int(data.get("active_employees_count", record.remote_active_employees or 0))
                    record.with_context(skip_remote_sync=True).write({
                        "remote_active_employees": remote_count,
                        "last_sync_at": fields.Datetime.now(),
                    })
                    if log_chatter:
                        record.message_post(
                            body=_(
                                "✅ تمت مزامنة الاشتراك والمميزات بنجاح مع سيرفر العميل (%s) — الحالة: %s — الحد الأقصى: %s موظف — الموظفون المفعّلون حالياً لدى العميل: %s"
                            )
                            % (target_url, record.state, record.max_employees, remote_count)
                        )
            except Exception as exc:
                _logger.warning("Failed to sync subscription %s to %s: %s", record.company_code, target_url, exc)
                if log_chatter:
                    record.message_post(
                        body=_("⚠️ تعذر الاتصال بسيرفر العميل (%s): %s") % (target_url, exc)
                    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_remote_sync"):
            records._sync_to_client_server(log_chatter=False)
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_remote_sync"):
            self._sync_to_client_server(log_chatter=False)
        return res

    def action_sync_client(self):
        self._sync_to_client_server(log_chatter=True)
        return True

    @api.model
    def _cron_expire_subscriptions(self):
        """Daily cron to automatically expire subscriptions past end_date and sync external client servers."""
        today = fields.Date.context_today(self)
        expired = self.sudo().search([
            ("state", "in", ["trial", "active"]),
            ("end_date", "!=", False),
            ("end_date", "<", today),
        ])
        if expired:
            expired.write({"state": "expired"})
        active_external = self.sudo().search([
            ("hosting_type", "=", "external_odoo"),
            ("state", "in", ["trial", "active"]),
        ])
        if active_external:
            active_external._sync_to_client_server(log_chatter=False)

