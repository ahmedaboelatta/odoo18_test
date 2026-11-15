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
        if sub:
            res["license_key"] = sub.license_key or icp.get_param("hader_mobile.license_key", "")
            res["company_code"] = sub.company_code
            res["subscription_state"] = sub.state
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
            res["license_key"] = icp.get_param("hader_mobile.license_key", "")
        return res

    def action_save_settings(self):
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("hader_mobile.api_enabled", "True" if self.api_enabled else "False")
        icp.set_param("hader_mobile.auth_provider", self.auth_provider or "password")
        if self.central_saas_url:
            icp.set_param("hader_mobile.central_saas_url", self.central_saas_url.strip())
        if self.license_key:
            icp.set_param("hader_mobile.license_key", self.license_key.strip())
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "تم حفظ الإعدادات / Settings Saved",
                "message": "تم تحديث إعدادات الربط والترخيص لتطبيق حاضر بنجاح.",
                "type": "success",
                "sticky": False,
            },
        }

