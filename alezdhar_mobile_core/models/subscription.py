from datetime import timedelta
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, ValidationError


class AlezdharMobileSubscription(models.Model):
    _name = "alezdhar.mobile.subscription"
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
            ("18.0", "Odoo 18"),
            ("17.0", "Odoo 17"),
            ("16.0", "Odoo 16"),
        ],
        string="إصدار أودو / Odoo Version",
        default="18.0",
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
    plan_type = fields.Selection(
        [
            ("trial", "باقة تجريبية (Trial)"),
            ("basic", "الباقة الأساسية (Basic)"),
            ("pro", "الباقة الاحترافية (Pro)"),
            ("enterprise", "باقة المؤسسات (Enterprise)"),
        ],
        string="نوع الباقة / Plan",
        required=True,
        default="pro",
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
    license_key = fields.Char(
        string="مفتاح الترخيص / License Key",
        readonly=True,
        copy=False,
        default=lambda self: f"HDR-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}",
    )
    notes = fields.Text(string="ملاحظات / Notes")

    _sql_constraints = [
        (
            "company_code_unique",
            "UNIQUE(company_code)",
            "Company code must be unique across all subscriptions.",
        ),
    ]

    @api.constrains("max_employees")
    def _check_max_employees(self):
        for record in self:
            if record.max_employees < 1:
                raise ValidationError(_("الحد الأقصى لعدد الموظفين يجب أن يكون 1 على الأقل."))

    @api.depends("company_id", "max_employees")
    def _compute_seat_usage(self):
        Identity = self.env["alezdhar.mobile.identity"].sudo()
        for record in self:
            if record.company_id:
                used = Identity.search_count([
                    ("company_id", "=", record.company_id.id),
                    ("active", "=", True),
                    ("state", "!=", "revoked"),
                ])
            else:
                used = 0
            record.active_employees_count = used
            record.remaining_seats = max(0, record.max_employees - used)
            record.usage_percentage = (
                min(100.0, round((used / record.max_employees) * 100.0, 1))
                if record.max_employees > 0
                else 0.0
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("company_code"):
                vals["company_code"] = str(vals["company_code"]).strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if "company_code" in vals and vals["company_code"]:
            vals["company_code"] = str(vals["company_code"]).strip().upper()
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

    def tenant_dto(self):
        self.ensure_one()
        logo = self.logo
        if not logo and self.company_id:
            branding = self.env["alezdhar.mobile.branding"].sudo().search(
                [("company_id", "=", self.company_id.id), ("active", "=", True)], limit=1
            )
            if branding and branding.logo:
                logo = branding.logo
            elif self.company_id.logo:
                logo = self.company_id.logo
        if isinstance(logo, bytes):
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
            "state": self.state,
            "plan_type": self.plan_type,
            "max_employees": self.max_employees,
            "active_employees": self.active_employees_count,
        }

    @api.model
    def verify_company_subscription(self, company, check_new_seat=False):
        """Enforce subscription validity and employee seat limit for a company."""
        sub = self.sudo().search([("company_id", "=", company.id)], order="id desc", limit=1)
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
            active_count = self.env["alezdhar.mobile.identity"].sudo().search_count([
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
