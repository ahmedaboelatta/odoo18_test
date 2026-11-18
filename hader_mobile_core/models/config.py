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


class HaderMobileClientSettings(models.Model):
    _name = "hader.mobile.client.settings"
    _description = "Hader Mobile Client Configuration (إعدادات ترخيص وربط تطبيق العميل)"
    _rec_name = "company_code"
    _order = "id desc"

    company_id = fields.Many2one(
        "res.company",
        string="الشركة في أودو (Odoo Company)",
        default=lambda self: self.env.company,
        required=True,
    )
    company_code = fields.Char(
        string="كود الشركة (Company Code)",
        required=True,
        help="كود الشركة المسلّم لكم من إدارة اشتراكات حاضر (مثال: ODOO20 أو EZDHAR).",
    )
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
        default="https://mustashark.tech",
        required=True,
    )
    license_key = fields.Char(
        string="مفتاح الترخيص الخاص بالشركة (Company License Key)",
        required=True,
        help="مفتاح الترخيص الفريد (HDR-XXXX-XXXX-XXXX) الصادر من خادم إدارة اشتراكات حاضر.",
    )
    subscription_state = fields.Selection(
        [
            ("trial", "تجريبي (Trial)"),
            ("active", "نشط (Active)"),
            ("suspended", "موقوف (Suspended)"),
            ("expired", "منتهي (Expired)"),
        ],
        string="حالة الاشتراك (Subscription Status)",
        compute="_compute_live_status",
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
        compute="_compute_live_status",
        readonly=True,
    )
    max_employees = fields.Integer(
        string="الحد الأقصى للموظفين (Max Employees)",
        compute="_compute_live_status",
        readonly=True,
    )
    active_employees_count = fields.Integer(
        string="الموظفون المفعّلون حالياً (Active Employees)",
        compute="_compute_live_status",
        readonly=True,
    )
    end_date = fields.Date(
        string="تاريخ انتهاء الاشتراك (Expiry Date)",
        compute="_compute_live_status",
        readonly=True,
    )
    days_remaining = fields.Integer(
        string="الأيام المتبقية (Days Remaining)",
        compute="_compute_live_status",
        readonly=True,
    )
    is_expiring_soon = fields.Boolean(
        string="قارب على الانتهاء (<= 15 يوم)",
        compute="_compute_live_status",
        readonly=True,
    )
    is_license_mismatch = fields.Boolean(
        string="مفتاح الترخيص غير متطابق",
        compute="_compute_live_status",
        readonly=True,
    )
    enabled_features_summary = fields.Char(
        string="المميزات المفعّلة في باقتكم (Enabled Plan Features)",
        compute="_compute_live_status",
        readonly=True,
    )

    def _find_matching_subscription(self, code=None):
        Sub = self.env["hader.mobile.subscription"].sudo()
        norm_code = (code or self.company_code or "").strip().upper()
        if norm_code:
            sub = Sub.search([("company_code", "=", norm_code)], order="id desc", limit=1)
            if sub:
                return sub
        if self.company_id:
            sub = Sub.search([("company_id", "=", self.company_id.id)], order="id desc", limit=1)
            if sub and not norm_code:
                return sub
        return Sub.browse()

    def _get_live_status_dict(self):
        self.ensure_one()
        sub = self._find_matching_subscription()
        configured_key = (self.license_key or "").strip()
        if sub:
            expected_key = (sub.license_key or "").strip()
            mismatch = bool(expected_key and configured_key != expected_key)
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
            return {
                "is_license_mismatch": mismatch,
                "subscription_state": "suspended" if mismatch else sub.state,
                "subscription_plan": sub.plan_type,
                "max_employees": sub.max_employees,
                "active_employees_count": sub.active_employees_count,
                "end_date": sub.end_date,
                "days_remaining": sub.days_remaining,
                "is_expiring_soon": sub.is_expiring_soon,
                "enabled_features_summary": " • ".join(labels) if labels else "لا توجد مميزات مفعلة",
            }
        return {
            "is_license_mismatch": False,
            "subscription_state": False,
            "subscription_plan": False,
            "max_employees": 0,
            "active_employees_count": 0,
            "end_date": False,
            "days_remaining": 0,
            "is_expiring_soon": False,
            "enabled_features_summary": "لا توجد مميزات مفعلة",
        }

    @api.depends("company_code", "license_key", "company_id")
    def _compute_live_status(self):
        for rec in self:
            if not rec.company_code and not rec.id:
                rec.is_license_mismatch = False
                rec.subscription_state = False
                rec.subscription_plan = False
                rec.max_employees = 0
                rec.active_employees_count = 0
                rec.end_date = False
                rec.days_remaining = 0
                rec.is_expiring_soon = False
                rec.enabled_features_summary = "لا توجد مميزات مفعلة"
                continue
            vals = rec._get_live_status_dict()
            rec.is_license_mismatch = vals["is_license_mismatch"]
            rec.subscription_state = vals["subscription_state"]
            rec.subscription_plan = vals["subscription_plan"]
            rec.max_employees = vals["max_employees"]
            rec.active_employees_count = vals["active_employees_count"]
            rec.end_date = vals["end_date"]
            rec.days_remaining = vals["days_remaining"]
            rec.is_expiring_soon = vals["is_expiring_soon"]
            rec.enabled_features_summary = vals["enabled_features_summary"]

    def _verify_and_sync_license_record(self):
        import json
        import ssl
        import urllib.request

        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        entered_code = (self.company_code or "").strip().upper()
        entered_key = (self.license_key or "").strip()
        if not entered_code:
            raise ValidationError(
                _("يرجى إدخال كود الشركة (Company Code) المسلم لكم من إدارة اشتراكات حاضر.")
            )
        if not entered_key:
            raise ValidationError(
                _("يرجى إدخال مفتاح الترخيص الخاص بالشركة (Company License Key).")
            )

        Sub = self.env["hader.mobile.subscription"].sudo()
        sub = Sub.search([("company_code", "=", entered_code)], order="id desc", limit=1)

        # 1. Check if a local subscription with this exact company_code already matches entered_key
        matched_verified = bool(sub and sub.license_key and entered_key == sub.license_key.strip())
        if matched_verified and sub:
            if self.company_id and sub.company_id != self.company_id:
                sub.with_context(skip_remote_sync=True).write({"company_id": self.company_id.id})
            sub.apply_features_to_local_flags()

        # 2. Otherwise, verify against Central SaaS Server (/hader/api/v1/saas/verify-license)
        if not matched_verified:
            base_url = (self.central_saas_url or "").strip().rstrip("/")
            candidate_urls = []
            if base_url:
                candidate_urls.append(base_url)
                if not base_url.endswith("/odoo20"):
                    candidate_urls.append(f"{base_url}/odoo20")
            for fallback_url in (
                "https://mustashark.tech",
                "https://81.208.161.238",
                "http://81.208.161.238:8069",
                "https://odoo-test.ezdharpos.com/odoo20",
            ):
                if fallback_url not in candidate_urls:
                    candidate_urls.append(fallback_url)
            ssl_ctx = ssl._create_unverified_context()
            for c_url in candidate_urls:
                verify_url = f"{c_url}/hader/api/v1/saas/verify-license"
                payload = {
                    "license_key": entered_key,
                    "company_code": entered_code,
                }
                req = urllib.request.Request(
                    verify_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=6, context=ssl_ctx) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        if body.get("status") == "success":
                            matched_verified = True
                            data = body.get("data") or {}
                            sub_vals = {
                                "company_code": entered_code,
                                "name": data.get("name") or entered_code,
                                "name_en": data.get("name_en") or data.get("name") or entered_code,
                                "license_key": data.get("license_key") or entered_key,
                                "state": data.get("state") or "active",
                                "plan_type": data.get("plan_type") or "enterprise",
                                "max_employees": int(data.get("max_employees") or 50),
                                "company_id": (self.company_id or self.env.company).id,
                                "last_sync_at": fields.Datetime.now(),
                            }
                            if data.get("start_date"):
                                sub_vals["start_date"] = data["start_date"]
                            if data.get("end_date"):
                                sub_vals["end_date"] = data["end_date"]
                            for feat_key in (
                                "feature_attendance",
                                "feature_leaves",
                                "feature_expenses",
                                "feature_services",
                                "feature_payroll",
                                "feature_notifications",
                                "feature_calendar",
                                "feature_custody",
                                "feature_tasks",
                                "feature_team_attendance",
                                "feature_directory",
                                "feature_loans",
                                "feature_contract",
                            ):
                                if feat_key in data:
                                    sub_vals[feat_key] = bool(data[feat_key])
                            if sub:
                                sub.with_context(skip_remote_sync=True).write(sub_vals)
                            else:
                                sub = Sub.with_context(skip_remote_sync=True).create(sub_vals)
                            sub.apply_features_to_local_flags()
                            break
                except Exception:
                    continue

        if not matched_verified:
            raise ValidationError(
                _(
                    "❌ بيانات الاشتراك المدخلة غير صحيحة!\n"
                    "كود الشركة (%s) أو مفتاح الترخيص (%s) لا يطابق البيانات المعتمدة في خادم إدارة الاشتراكات.\n"
                    "يرجى التأكد من إدخال كود الشركة ومفتاح الترخيص الصحيحين."
                )
                % (entered_code, entered_key)
            )

        icp.set_param("hader_mobile.api_enabled", "True" if self.api_enabled else "False")
        icp.set_param("hader_mobile.auth_provider", self.auth_provider or "password")
        if self.central_saas_url:
            icp.set_param("hader_mobile.central_saas_url", self.central_saas_url.strip())
        icp.set_param("hader_mobile.license_key", entered_key)
        icp.set_param("hader_mobile.company_code", entered_code)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("company_code"):
                vals["company_code"] = str(vals["company_code"]).strip().upper()
            if vals.get("license_key"):
                vals["license_key"] = str(vals["license_key"]).strip()
        records = super().create(vals_list)
        if not self.env.context.get("skip_license_verify"):
            for rec in records:
                rec._verify_and_sync_license_record()
        return records

    def write(self, vals):
        if "company_code" in vals and vals["company_code"]:
            vals["company_code"] = str(vals["company_code"]).strip().upper()
        if "license_key" in vals and vals["license_key"]:
            vals["license_key"] = str(vals["license_key"]).strip()
        res = super().write(vals)
        if not self.env.context.get("skip_license_verify") and any(
            k in vals for k in ("company_code", "license_key", "central_saas_url", "api_enabled", "auth_provider")
        ):
            for rec in self:
                rec._verify_and_sync_license_record()
        return res

    def action_save_settings(self):
        self.ensure_one()
        self._verify_and_sync_license_record()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "تم حفظ وتفعيل الاشتراك بنجاح / Subscription Activated",
                "message": f"تم التحقق من كود الشركة ({self.company_code}) ومفتاح الترخيص وتفعيل الباقة بنجاح.",
                "type": "success",
                "sticky": False,
            },
        }

