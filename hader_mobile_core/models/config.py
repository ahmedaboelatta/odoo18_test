from odoo import api, fields, models


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
    _description = "Hader Mobile Client Configuration (إعدادات تطبيق العميل)"

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
    master_secret = fields.Char(
        string="مفتاح الربط السري مع خادم الاشتراكات (Master Sync Secret)",
    )
    company_code = fields.Char(string="كود الشركة الحالي (Company Code)", readonly=True)
    subscription_state = fields.Char(string="حالة الاشتراك (Subscription Status)", readonly=True)
    subscription_plan = fields.Char(string="الباقة الحالية (Current Plan)", readonly=True)
    max_employees = fields.Integer(string="الحد الأقصى للموظفين (Max Employees)", readonly=True)
    end_date = fields.Date(string="تاريخ انتهاء الاشتراك (Expiry Date)", readonly=True)

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
        res["master_secret"] = icp.get_param(
            "hader_mobile.master_secret", "HADER-SAAS-MASTER-2026-SECRET"
        )
        sub = self.env["hader.mobile.subscription"].sudo().search(
            [("company_id", "=", self.env.company.id)], order="id desc", limit=1
        )
        if not sub:
            sub = self.env["hader.mobile.subscription"].sudo().search([], order="id desc", limit=1)
        if sub:
            res["company_code"] = sub.company_code
            res["subscription_state"] = sub.state
            res["subscription_plan"] = sub.plan_type
            res["max_employees"] = sub.max_employees
            res["end_date"] = sub.end_date
        return res

    def action_save_settings(self):
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("hader_mobile.api_enabled", "True" if self.api_enabled else "False")
        icp.set_param("hader_mobile.auth_provider", self.auth_provider or "password")
        if self.central_saas_url:
            icp.set_param("hader_mobile.central_saas_url", self.central_saas_url.strip())
        if self.master_secret:
            icp.set_param("hader_mobile.master_secret", self.master_secret.strip())
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "تم حفظ الإعدادات / Settings Saved",
                "message": "تم تحديث إعدادات الربط والمصادقة لتطبيق حاضر بنجاح.",
                "type": "success",
                "sticky": False,
            },
        }

