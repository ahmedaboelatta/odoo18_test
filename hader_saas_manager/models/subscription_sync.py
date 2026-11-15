import base64
import json
import logging
import secrets
import urllib.request

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

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
                saved_local_key = (
                    self.env["ir.config_parameter"]
                    .sudo()
                    .get_param("hader_mobile.license_key", "")
                    or ""
                ).strip()
                if saved_local_key and record.license_key and saved_local_key != record.license_key.strip():
                    if log_chatter:
                        raise ValidationError(
                            _(
                                "❌ تعذرت المزامنة: مفتاح الترخيص المحفوظ في إعدادات العميل لا يطابق مفتاح الترخيص الجديد للشركة (%s).\nيرجى نسخ مفتاح الترخيص الجديد ووضعه في شاشة (إعدادات الربط والمصادقة) لدى العميل أولاً."
                            )
                            % record.license_key
                        )
                    continue
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
                "feature_loans": bool(record.feature_loans),
                "feature_contract": bool(record.feature_contract),
                "license_key": record.license_key,
                "welcome_text_ar": record.welcome_text_ar or "مرحباً بك",
                "welcome_text_en": record.welcome_text_en or "Welcome",
                "primary_color": record.primary_color or "#171717",
                "accent_color": record.accent_color or "#D6A34A",
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Hader-Master-Secret": secret,
                "X-Hader-License-Key": record.license_key or "",
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
                err_msg = str(exc)
                if hasattr(exc, "read"):
                    try:
                        err_body = json.loads(exc.read().decode("utf-8"))
                        err_msg = (err_body.get("error") or {}).get("message") or err_msg
                    except Exception:
                        pass
                _logger.warning("Failed to sync subscription %s to %s: %s", record.company_code, target_url, err_msg)
                if log_chatter:
                    record.message_post(
                        body=_("⚠️ تعذرت المزامنة مع سيرفر العميل (%s): %s") % (target_url, err_msg)
                    )
                    raise ValidationError(
                        _("تعذرت المزامنة مع سيرفر العميل (%s):\n%s") % (target_url, err_msg)
                    ) from exc

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


class HaderSaasSettings(models.TransientModel):
    _name = "hader.saas.settings"
    _description = "Hader SaaS Central Server Configuration (إعدادات خادم الاشتراكات المركزي)"

    central_saas_url = fields.Char(
        string="رابط خادم الاشتراكات المركزي (Central SaaS URL)",
        default="https://odoo-test.ezdharpos.com/odoo20",
        required=True,
    )
    master_secret = fields.Char(
        string="مفتاح المزامنة السري الموحد (Master Sync Secret)",
        required=True,
        help="Secret key sent in X-Hader-Master-Secret header when pushing subscription updates to client Odoo servers.",
    )
    default_plan_type = fields.Selection(
        [
            ("trial", "باقة تجريبية (Trial)"),
            ("basic", "الباقة الأساسية (Basic)"),
            ("pro", "الباقة الاحترافية (Pro)"),
            ("enterprise", "باقة المؤسسات (Enterprise)"),
        ],
        string="الباقة الافتراضية للاشتراكات الجديدة (Default Plan)",
        default="enterprise",
        required=True,
    )
    default_max_employees = fields.Integer(
        string="الحد الافتراضي للموظفين (Default Max Employees)",
        default=50,
        required=True,
    )
    total_subscriptions = fields.Integer(string="إجمالي الاشتراكات المسجلة", readonly=True)
    active_subscriptions = fields.Integer(string="الاشتراكات النشطة حالياً", readonly=True)
    expired_or_suspended = fields.Integer(string="الاشتراكات المنتهية / الموقوفة", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        self.sudo().search([("create_uid", "=", self.env.uid)]).unlink()
        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        icp = self.env["ir.config_parameter"].sudo()
        res["central_saas_url"] = icp.get_param(
            "hader_mobile.central_saas_url", "https://odoo-test.ezdharpos.com/odoo20"
        )
        res["master_secret"] = icp.get_param(
            "hader_mobile.master_secret", DEFAULT_MASTER_SECRET
        )
        res["default_plan_type"] = icp.get_param(
            "hader_saas.default_plan_type", "enterprise"
        )
        res["default_max_employees"] = int(
            icp.get_param("hader_saas.default_max_employees", "50") or 50
        )
        Sub = self.env["hader.mobile.subscription"].sudo()
        res["total_subscriptions"] = Sub.search_count([])
        res["active_subscriptions"] = Sub.search_count([("state", "in", ["active", "trial"])])
        res["expired_or_suspended"] = Sub.search_count([("state", "in", ["expired", "suspended"])])
        return res

    def action_save_saas_settings(self):
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("hader_mobile.central_saas_url", (self.central_saas_url or "").strip())
        icp.set_param("hader_mobile.master_secret", (self.master_secret or "").strip())
        icp.set_param("hader_saas.default_plan_type", self.default_plan_type or "enterprise")
        icp.set_param("hader_saas.default_max_employees", str(self.default_max_employees or 50))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "تم حفظ إعدادات الاشتراكات / SaaS Settings Saved",
                "message": "تم حفظ إعدادات خادم الاشتراكات المركزي ومفتاح المزامنة بنجاح.",
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_all_clients(self):
        self.ensure_one()
        self.action_save_saas_settings()
        subs = self.env["hader.mobile.subscription"].sudo().search([])
        if subs:
            subs._sync_to_client_server(log_chatter=True)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "تمت المزامنة الشاملة / All Clients Synced",
                "message": f"تمت مزامنة جميع الاشتراكات ({len(subs)}) مع خوادم العملاء بنجاح.",
                "type": "info",
                "sticky": False,
            },
        }

    def action_new_subscription(self):
        return {
            "type": "ir.actions.act_window",
            "name": "إضافة اشتراك شركة جديدة (New Company Subscription)",
            "res_model": "hader.mobile.subscription",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_plan_type": self.default_plan_type or "enterprise",
                "default_max_employees": self.default_max_employees or 50,
            },
        }

    def action_open_subscriptions_list(self):
        return {
            "type": "ir.actions.act_window",
            "name": "اشتراكات الشركات (Hader Subscriptions)",
            "res_model": "hader.mobile.subscription",
            "view_mode": "list,kanban,form,graph,pivot",
            "target": "current",
        }


