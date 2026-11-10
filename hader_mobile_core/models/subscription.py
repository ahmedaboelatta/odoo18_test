import base64
from datetime import timedelta
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, ValidationError


PLAN_FEATURE_PRESETS = {
    "basic": {
        "feature_attendance": True,
        "feature_leaves": True,
        "feature_expenses": False,
        "feature_services": False,
        "feature_payroll": False,
        "feature_notifications": False,
        "feature_calendar": False,
    },
    "pro": {
        "feature_attendance": True,
        "feature_leaves": True,
        "feature_expenses": True,
        "feature_services": True,
        "feature_payroll": False,
        "feature_notifications": True,
        "feature_calendar": True,
    },
    "enterprise": {
        "feature_attendance": True,
        "feature_leaves": True,
        "feature_expenses": True,
        "feature_services": True,
        "feature_payroll": True,
        "feature_notifications": True,
        "feature_calendar": True,
    },
    "trial": {
        "feature_attendance": True,
        "feature_leaves": True,
        "feature_expenses": True,
        "feature_services": True,
        "feature_payroll": True,
        "feature_notifications": True,
        "feature_calendar": True,
    },
}


class HaderMobileSubscription(models.Model):
    _name = "hader.mobile.subscription"
    _description = "Hader Mobile SaaS Subscription"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="اسم الشركة (عربي) / Company Name (AR)", required=True, tracking=True)
    name_en = fields.Char(string="اسم الشركة (إنجليزي) / Company Name (EN)", tracking=True)
    company_code = fields.Char(
        string="كود الشركة / Company Code",
        required=True,
        index=True,
        copy=False,
        tracking=True,
        help="Unique short code entered by employees in the Hader app (e.g. EZDHAR).",
    )
    logo = fields.Image(
        string="شعار الشركة / Company Logo",
        max_width=512,
        max_height=512,
        help="Logo displayed to employees in the app after entering this company code.",
    )
    hosting_type = fields.Selection(
        [
            ("cloud_shared", "استضافة لدينا (Cloud SaaS على سيرفرنا)"),
            ("external_odoo", "استضافة لدى العميل (سيرفر أودو خارجي خاص بالعميل)"),
        ],
        string="نوع الاستضافة / Hosting Type",
        required=True,
        default="cloud_shared",
        tracking=True,
    )
    odoo_version = fields.Selection(
        [
            ("20.0", "Odoo 20"),
            ("19.0", "Odoo 19"),
            ("18.0", "Odoo 18"),
            ("17.0", "Odoo 17"),
            ("16.0", "Odoo 16"),
        ],
        string="إصدار أودو / Odoo Version",
        default="20.0",
        required=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="الشركة في أودو / Odoo Company",
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    contact_name = fields.Char(string="اسم المسؤول / Contact Person")
    contact_phone = fields.Char(string="رقم التواصل / Contact Phone")
    contact_email = fields.Char(string="البريد الإلكتروني / Contact Email")
    server_url = fields.Char(
        string="رابط السيرفر / Odoo Server URL",
        default="https://odoo-test.ezdharpos.com",
        help="Target Odoo server URL for this client company.",
    )
    db_name = fields.Char(
        string="اسم قاعدة البيانات / Database Name (اختياري)",
        help="Optional database name on the client server (needed only if the server hosts multiple databases on the same domain).",
    )
    plan_type = fields.Selection(
        [
            ("trial", "باقة تجريبية (Trial — جميع المميزات)"),
            ("basic", "الباقة الأساسية (Basic — حضور + إجازات)"),
            ("pro", "الباقة الاحترافية (Pro — حضور + إجازات + طلبات + إشعارات)"),
            ("enterprise", "باقة المؤسسات (Enterprise — شاملة الرواتب وجميع المميزات)"),
        ],
        string="نوع الباقة / Plan",
        required=True,
        default="enterprise",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("trial", "تجريبي (Trial)"),
            ("active", "نشط (Active)"),
            ("suspended", "موقوف (Suspended)"),
            ("expired", "منتهي (Expired)"),
        ],
        string="حالة الاشتراك / Status",
        required=True,
        default="active",
        tracking=True,
    )
    start_date = fields.Date(
        string="تاريخ البداية / Start Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    end_date = fields.Date(
        string="تاريخ الانتهاء / End Date",
        required=True,
        default=lambda self: fields.Date.context_today(self) + timedelta(days=365),
        tracking=True,
    )
    max_employees = fields.Integer(
        string="الحد الأقصى للموظفين / Max Employees",
        required=True,
        default=50,
        tracking=True,
    )
    remote_active_employees = fields.Integer(
        string="الموظفون المفعّلون على سيرفر العميل",
        default=0,
        copy=False,
    )
    last_sync_at = fields.Datetime(
        string="آخر مزامنة مع السيرفر / Last Sync",
        readonly=True,
        copy=False,
    )
    active_employees_count = fields.Integer(
        string="الموظفون المفعّلون حالياً / Active Employees",
        compute="_compute_seat_usage",
    )
    remaining_seats = fields.Integer(
        string="المقاعد المتبقية / Remaining Seats",
        compute="_compute_seat_usage",
    )
    usage_percentage = fields.Float(
        string="نسبة استهلاك الباقة (%)",
        compute="_compute_seat_usage",
    )
    feature_attendance = fields.Boolean(
        string="الحضور والانصراف وشفتاتي (Attendance & Shifts)",
        default=True,
        tracking=True,
    )
    feature_leaves = fields.Boolean(
        string="الإجازات (Time Off / Leaves)",
        default=True,
        tracking=True,
    )
    feature_expenses = fields.Boolean(
        string="المصاريف والعهد المالية (Expenses)",
        default=True,
        tracking=True,
    )
    feature_services = fields.Boolean(
        string="خدمات وطلبات الموظفين (Employee Services)",
        default=True,
        tracking=True,
    )
    feature_payroll = fields.Boolean(
        string="قسائم الرواتب (Payroll Payslips)",
        default=True,
        tracking=True,
    )
    feature_notifications = fields.Boolean(
        string="الإشعارات والتعاميم (Notifications)",
        default=True,
        tracking=True,
    )
    feature_calendar = fields.Boolean(
        string="التقويم والاجتماعات (Calendar & Meetings)",
        default=True,
        tracking=True,
    )
    license_key = fields.Char(
        string="مفتاح الترخيص / License Key",
        readonly=True,
        copy=False,
        default=lambda self: f"HDR-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}",
    )
    notes = fields.Text(string="ملاحظات / Notes")

    if hasattr(models, "Constraint"):
        _company_code_unique = models.Constraint(
            "UNIQUE(company_code)",
            "Company code must be unique across all subscriptions.",
        )
    else:
        _sql_constraints = [
            ("company_code_unique", "UNIQUE(company_code)", "Company code must be unique across all subscriptions."),
        ]

    @api.onchange("plan_type")
    def _onchange_plan_type(self):
        preset = PLAN_FEATURE_PRESETS.get(self.plan_type)
        if preset:
            for field_name, val in preset.items():
                setattr(self, field_name, val)

    @api.constrains("max_employees")
    def _check_max_employees(self):
        for record in self:
            if record.max_employees < 1:
                raise ValidationError(_("الحد الأقصى لعدد الموظفين يجب أن يكون 1 على الأقل."))

    @api.depends("company_id", "max_employees", "hosting_type", "remote_active_employees")
    def _compute_seat_usage(self):
        Identity = self.env["hader.mobile.identity"].sudo()
        for record in self:
            if record.hosting_type == "external_odoo" and record.remote_active_employees > 0:
                used = record.remote_active_employees
            elif record.company_id:
                used = Identity.search_count([
                    ("company_id", "=", record.company_id.id),
                    ("active", "=", True),
                    ("state", "!=", "revoked"),
                ])
                if used == 0 and record.remote_active_employees > 0:
                    used = record.remote_active_employees
            else:
                used = record.remote_active_employees or 0
            record.active_employees_count = used
            record.remaining_seats = max(0, record.max_employees - used)
            record.usage_percentage = (
                min(100.0, round((used / record.max_employees) * 100.0, 1))
                if record.max_employees > 0
                else 0.0
            )

    @api.model_create_multi
    def create(self, vals_list):
        feature_keys = set(PLAN_FEATURE_PRESETS["enterprise"].keys())
        for vals in vals_list:
            if vals.get("company_code"):
                vals["company_code"] = str(vals["company_code"]).strip().upper()
            plan = vals.get("plan_type")
            if plan in PLAN_FEATURE_PRESETS and not feature_keys.intersection(vals.keys()):
                vals.update(PLAN_FEATURE_PRESETS[plan])
        return super().create(vals_list)

    def write(self, vals):
        if "company_code" in vals and vals["company_code"]:
            vals["company_code"] = str(vals["company_code"]).strip().upper()
        feature_keys = set(PLAN_FEATURE_PRESETS["enterprise"].keys())
        if "plan_type" in vals and vals["plan_type"] in PLAN_FEATURE_PRESETS and not feature_keys.intersection(vals.keys()):
            vals = dict(vals, **PLAN_FEATURE_PRESETS[vals["plan_type"]])
        return super().write(vals)

    def action_activate(self):
        self.write({"state": "active"})

    def action_suspend(self):
        self.write({"state": "suspended"})

    def action_renew_year(self):
        today = fields.Date.context_today(self)
        for record in self:
            base_date = record.end_date if record.end_date and record.end_date > today else today
            record.write({
                "end_date": base_date + timedelta(days=365),
                "state": "active",
            })

    def action_regenerate_license_key(self):
        for record in self:
            record.write({
                "license_key": f"HDR-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            })

    def apply_features_to_local_flags(self):
        """Sync subscription feature toggles onto local hader.mobile.feature records on client server."""
        self.ensure_one()
        mapping = {
            "attendance": (self.feature_attendance, "Attendance", 10),
            "leaves": (self.feature_leaves, "Time Off / Leaves", 15),
            "expenses": (self.feature_expenses, "Expenses", 18),
            "services": (self.feature_services, "Employee Services", 20),
            "payroll": (self.feature_payroll, "Payroll", 30),
            "notifications": (self.feature_notifications, "Notifications", 40),
            "calendar": (self.feature_calendar, "Calendar & Meetings", 50),
        }
        Feature = self.env["hader.mobile.feature"].sudo()
        for key, (enabled, label, seq) in mapping.items():
            feat = Feature.search([("key", "=", key)], limit=1)
            if feat:
                if feat.enabled != bool(enabled):
                    feat.write({"enabled": bool(enabled)})
            else:
                Feature.create({
                    "name": label,
                    "key": key,
                    "sequence": seq,
                    "enabled": bool(enabled),
                })

    def features_dto(self):
        self.ensure_one()
        base_features = self.env["hader.mobile.feature"].sudo().bootstrap_dto()
        overrides = {
            "attendance": bool(self.feature_attendance),
            "leaves": bool(self.feature_leaves),
            "expenses": bool(self.feature_expenses),
            "services": bool(self.feature_services),
            "payroll": bool(self.feature_payroll),
            "notifications": bool(self.feature_notifications),
            "calendar": bool(self.feature_calendar),
        }
        seen = set()
        for item in base_features:
            k = item.get("key")
            if k in overrides:
                item["enabled"] = overrides[k]
                seen.add(k)
        for k, enabled in overrides.items():
            if k not in seen:
                base_features.append({
                    "key": k,
                    "enabled": enabled,
                    "minimum_app_version": "0.1.0",
                })
        return base_features

    def tenant_dto(self):
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
            logo = base64.b64encode(logo.content).decode("ascii") if logo.content else None
        elif isinstance(logo, bytes):
            logo = logo.decode("ascii")
        return {
            "company_code": self.company_code,
            "company_name": self.name,
            "company_name_ar": self.name,
            "company_name_en": self.name_en or self.name,
            "logo_base64": logo or None,
            "hosting_type": self.hosting_type,
            "odoo_version": self.odoo_version,
            "server_url": (self.server_url or "https://odoo-test.ezdharpos.com").rstrip("/"),
            "db_name": self.db_name or None,
            "state": self.state,
            "plan_type": self.plan_type,
            "max_employees": self.max_employees,
            "active_employees": self.active_employees_count,
            "features": {
                "attendance": bool(self.feature_attendance),
                "leaves": bool(self.feature_leaves),
                "expenses": bool(self.feature_expenses),
                "services": bool(self.feature_services),
                "payroll": bool(self.feature_payroll),
                "notifications": bool(self.feature_notifications),
                "calendar": bool(self.feature_calendar),
            },
        }

    @api.model
    def verify_company_subscription(self, company, check_new_seat=False):
        """Enforce subscription validity and employee seat limit for a company."""
        sub = self.sudo().search([("company_id", "=", company.id)], order="id desc", limit=1)
        if not sub:
            sub = self.sudo().search([], order="id desc", limit=1)
        if not sub:
            return True
        today = fields.Date.context_today(self)
        if sub.state == "suspended":
            raise ValidationError(
                _("تم إيقاف اشتراك الشركة مؤقتاً في نظام حاضر. يرجى التواصل مع الإدارة لتفعيل الاشتراك.")
            )
        if sub.state == "expired" or (sub.end_date and sub.end_date < today):
            if sub.state != "expired":
                sub.sudo().write({"state": "expired"})
            raise ValidationError(
                _("انتهت صلاحية اشتراك الشركة في نظام حاضر بتاريخ %s. يرجى تجديد الاشتراك.")
                % sub.end_date
            )
        if check_new_seat:
            active_count = self.env["hader.mobile.identity"].sudo().search_count([
                ("company_id", "=", company.id),
                ("active", "=", True),
                ("state", "!=", "revoked"),
            ])
            if active_count > sub.max_employees:
                raise ValidationError(
                    _("تم الوصول إلى الحد الأقصى لعدد الموظفين المسموح به في باقة الاشتراك الحالية (%s موظف). يرجى ترقية الباقة لإضافة موظفين جدد.")
                    % sub.max_employees
                )
        return True
