from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.model
    def get_param(self, key, default=False):
        if hasattr(super(), "get_param"):
            return super().get_param(key, default)
        return self.get_str(key, default)

    @api.model
    def set_param(self, key, value):
        if hasattr(super(), "set_param"):
            return super().set_param(key, value)
        return self.set_str(key, value)


class HaderMobileFeature(models.Model):
    _name = "hader.mobile.feature"
    _description = "Hader Mobile Feature"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, key"

    name = fields.Char(required=True, translate=True)
    key = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    enabled = fields.Boolean(default=False, tracking=True)
    minimum_app_version = fields.Char(default="0.1.0")
    requires_authentication = fields.Boolean(default=True)

    _sql_constraints = [("key_unique", "UNIQUE(key)", "Feature key must be unique.")]

    def write(self, vals):
        if "enabled" in vals and vals["enabled"] and not self.env.context.get("from_saas_sync"):
            sub = self.env["hader.mobile.subscription"].sudo().search(
                [("company_id", "=", self.env.company.id)], order="id desc", limit=1
            )
            if not sub:
                sub = self.env["hader.mobile.subscription"].sudo().search([], order="id desc", limit=1)
            if sub:
                for rec in self:
                    sub_field = f"feature_{rec.key}"
                    if sub_field in sub._fields and not getattr(sub, sub_field):
                        raise ValidationError(
                            _(
                                "لا يمكن تفعيل ميزة (%s) يدوياً لأنها مقفلة من خادم اشتراكات حاضر المركزي أو غير مشمولة في باقتكم الحالية."
                            )
                            % rec.name
                        )
        return super().write(vals)

    @api.model
    def bootstrap_dto(self):
        return [
            {
                "key": feature.key,
                "enabled": feature.enabled,
                "minimum_app_version": feature.minimum_app_version,
            }
            for feature in self.sudo().search([("active", "=", True)])
        ]


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hader_mobile_auth_provider = fields.Selection(
        [("disabled", "Disabled"), ("password", "Employee number and password")],
        string="Mobile authentication provider",
        default="disabled",
        config_parameter="hader_mobile.auth_provider",
    )
    hader_mobile_api_enabled = fields.Boolean(
        string="Enable authenticated mobile API",
        default=False,
        config_parameter="hader_mobile.api_enabled",
    )


class HaderMobileClientSettings(models.TransientModel):
    _name = "hader.mobile.client.settings"
    _description = "Hader Mobile Client Configuration (إعدادات ترخيص وربط تطبيق العميل)"

    api_enabled = fields.Boolean(
        string="تفعيل واجهة تطبيق الموبايل (Enable Mobile API)",
        default=True,
    )
    auth_provider = fields.Selection(
        [
            ("disabled", "معطّل (Disabled)"),
            ("password", "الرقم الوظيفي وكلمة المرور (Employee Number & Password)"),
        ],
        string="طريقة مصادقة الموظفين (Authentication Provider)",
        default="password",
        required=True,
    )
    central_saas_url = fields.Char(
        string="رابط خادم الاشتراكات المركزي (Central SaaS Server URL)",
        default="https://odoo-test.ezdharpos.com/odoo20",
    )
    license_key = fields.Char(
        string="مفتاح الترخيص الخاص بالشركة (Company License Key)",
        help="مفتاح الترخيص الفريد (HDR-XXXX-XXXX-XXXX) الصادر من خادم إدارة اشتراكات حاضر.",
    )
    company_code = fields.Char(string="كود الشركة (Company Code)", readonly=True)
    subscription_state = fields.Selection(
        [
            ("trial", "تجريبي (Trial)"),
            ("active", "نشط (Active)"),
            ("suspended", "موقوف (Suspended)"),
            ("expired", "منتهي (Expired)"),
        ],
        string="حالة الاشتراك (Subscription Status)",
        readonly=True,
    )
    subscription_plan = fields.Selection(
        [
            ("trial", "باقة تجريبية (Trial)"),
            ("basic", "الباقة الأساسية (Basic)"),
            ("pro", "الباقة الاحترافية (Pro)"),
            ("enterprise", "باقة المؤسسات (Enterprise)"),
        ],
        string="الباقة الحالية (Current Plan)",
        readonly=True,
    )
    max_employees = fields.Integer(string="الحد الأقصى للموظفين (Max Employees)", readonly=True)
    active_employees_count = fields.Integer(string="الموظفون المفعّلون حالياً (Active Employees)", readonly=True)
    end_date = fields.Date(string="تاريخ انتهاء الاشتراك (Expiry Date)", readonly=True)
    days_remaining = fields.Integer(string="الأيام المتبقية (Days Remaining)", readonly=True)
    is_expiring_soon = fields.Boolean(string="قارب على الانتهاء (<= 15 يوم)", readonly=True)
    is_license_mismatch = fields.Boolean(string="مفتاح الترخيص غير متطابق", readonly=True)
    enabled_features_summary = fields.Char(
        string="المميزات المفعّلة في باقتكم (Enabled Plan Features)",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        self.sudo().search([("create_uid", "=", self.env.uid)]).unlink()
        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        icp = self.env["ir.config_parameter"].sudo()
        enabled_raw = icp.get_param("hader_mobile.api_enabled", "True")
        res["api_enabled"] = enabled_raw in (True, "True", "1", 1)
        res["auth_provider"] = icp.get_param("hader_mobile.auth_provider", "password") or "password"
        res["central_saas_url"] = icp.get_param(
            "hader_mobile.central_saas_url", "https://odoo-test.ezdharpos.com/odoo20"
        )
        sub = self.env["hader.mobile.subscription"].sudo().search(
            [("company_id", "=", self.env.company.id)], order="id desc", limit=1
        )
        if not sub:
            sub = self.env["hader.mobile.subscription"].sudo().search([], order="id desc", limit=1)
        configured_key = (icp.get_param("hader_mobile.license_key", "") or "").strip()
        if sub:
            expected_key = (sub.license_key or "").strip()
            mismatch = bool(expected_key and configured_key != expected_key)
            res["license_key"] = configured_key or expected_key
            res["is_license_mismatch"] = mismatch
            res["company_code"] = sub.company_code
            res["subscription_state"] = "suspended" if mismatch else sub.state
            res["subscription_plan"] = sub.plan_type
            res["max_employees"] = sub.max_employees
            res["active_employees_count"] = sub.active_employees_count
            res["end_date"] = sub.end_date
            res["days_remaining"] = sub.days_remaining
            res["is_expiring_soon"] = sub.is_expiring_soon
            labels = []
            if sub.feature_attendance:
                labels.append("الحضور والانصراف")
            if sub.feature_leaves:
                labels.append("الإجازات")
            if sub.feature_expenses:
                labels.append("المصاريف")
            if sub.feature_services:
                labels.append("الطلبات والخدمات")
            if sub.feature_loans:
                labels.append("السلف المالية")
            if sub.feature_contract:
                labels.append("العقد والراتب")
            if sub.feature_payroll:
                labels.append("قسائم الرواتب")
            if sub.feature_custody:
                labels.append("العهد الشخصية")
            if sub.feature_tasks:
                labels.append("المهام اليومية")
            if sub.feature_directory:
                labels.append("دليل الموظفين")
            if sub.feature_notifications:
                labels.append("الإشعارات")
            res["enabled_features_summary"] = " • ".join(labels) if labels else "لا توجد مميزات مفعلة"
        else:
            res["license_key"] = configured_key
            res["is_license_mismatch"] = False
        return res

    def action_save_settings(self):
        import json
        import urllib.error
        import urllib.request

        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        entered_key = (self.license_key or "").strip()
        if not entered_key:
            raise ValidationError(
                _("يرجى إدخال مفتاح الترخيص الخاص بالشركة (Company License Key).")
            )

        sub = self.env["hader.mobile.subscription"].sudo().search(
            [("company_id", "=", self.env.company.id)], order="id desc", limit=1
        )
        if not sub:
            sub = self.env["hader.mobile.subscription"].sudo().search([], order="id desc", limit=1)

        # 1. If entered_key already matches local synced sub.license_key, it is valid!
        matched_verified = bool(sub and sub.license_key and entered_key == sub.license_key.strip())

        # 2. Otherwise (or in addition), check Central SaaS Server (including /odoo20 fallback if same domain)
        if not matched_verified and "hader.saas.settings" not in self.env:
            base_url = (self.central_saas_url or "").strip().rstrip("/")
            candidate_urls = []
            if base_url:
                if not base_url.endswith("/odoo20"):
                    candidate_urls.append(f"{base_url}/odoo20")
                candidate_urls.append(base_url)
            for c_url in candidate_urls:
                verify_url = f"{c_url}/hader/api/v1/saas/verify-license"
                payload = {
                    "license_key": entered_key,
                    "company_code": sub.company_code if sub else "",
                }
                req = urllib.request.Request(
                    verify_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=6) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        if body.get("status") == "success":
                            matched_verified = True
                            data = body.get("data") or {}
                            if sub and data.get("license_key"):
                                sub.with_context(skip_remote_sync=True).write({
                                    "license_key": data["license_key"],
                                    "state": data.get("state") or sub.state,
                                    "plan_type": data.get("plan_type") or sub.plan_type,
                                    "max_employees": int(data.get("max_employees") or sub.max_employees),
                                    "end_date": data.get("end_date") or sub.end_date,
                                })
                            break
                except Exception:
                    continue

        if not matched_verified:
            raise ValidationError(
                _(
                    "❌ مفتاح الترخيص المدخل (%s) غير صحيح أو لا يطابق مفتاح الترخيص المعتمد في خادم الاشتراكات!\nيرجى التأكد من نسخ مفتاح الترخيص الصحيح من لوحة إدارة الاشتراكات."
                )
                % entered_key
            )

        icp.set_param("hader_mobile.api_enabled", "True" if self.api_enabled else "False")
        icp.set_param("hader_mobile.auth_provider", self.auth_provider or "password")
        if self.central_saas_url:
            icp.set_param("hader_mobile.central_saas_url", self.central_saas_url.strip())
        icp.set_param("hader_mobile.license_key", entered_key)
        return {
            "type": "ir.actions.act_window",
            "name": "Subscription & API Status (حالة الاشتراك والربط)",
            "res_model": "hader.mobile.client.settings",
            "view_mode": "form",
            "target": "current",
        }

