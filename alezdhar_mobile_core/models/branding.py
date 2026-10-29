from odoo import api, fields, models


class AlezdharMobileBranding(models.Model):
    _name = "alezdhar.mobile.branding"
    _description = "Alezdhar Mobile Branding"
    _order = "company_id"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    active = fields.Boolean(default=True)
    app_name_ar = fields.Char(required=True, default="الازدهار")
    app_name_en = fields.Char(required=True, default="Alezdhar")
    logo = fields.Image(required=True, max_width=1024, max_height=1024)
    welcome_text_ar = fields.Char(default="مرحباً بك")
    welcome_text_en = fields.Char(default="Welcome")
    primary_color = fields.Char(default="#171717")
    accent_color = fields.Char(default="#D6A34A")
    version = fields.Integer(default=1, readonly=True)
    published_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "company_unique",
            "UNIQUE(company_id)",
            "Only one mobile branding record is allowed per company.",
        )
    ]

    def action_publish(self):
        for branding in self:
            branding.write(
                {
                    "version": branding.version + 1,
                    "published_at": fields.Datetime.now(),
                }
            )
        return True

    @api.model
    def public_dto(self):
        branding = self.sudo().search(
            [("company_id", "=", self.env.company.id), ("active", "=", True)],
            limit=1,
        )
        if not branding:
            return {
                "app_name_ar": "الازدهار",
                "app_name_en": "Alezdhar",
                "welcome_text_ar": "مرحباً بك",
                "welcome_text_en": "Welcome",
                "logo_base64": None,
                "primary_color": "#171717",
                "accent_color": "#D6A34A",
                "version": 0,
                "updated_at": None,
            }
        logo = branding.logo
        if isinstance(logo, bytes):
            logo = logo.decode()
        return {
            "app_name_ar": branding.app_name_ar,
            "app_name_en": branding.app_name_en,
            "welcome_text_ar": branding.welcome_text_ar,
            "welcome_text_en": branding.welcome_text_en,
            "logo_base64": logo or None,
            "primary_color": branding.primary_color,
            "accent_color": branding.accent_color,
            "version": branding.version,
            "updated_at": branding.published_at.isoformat()
            if branding.published_at
            else None,
        }
