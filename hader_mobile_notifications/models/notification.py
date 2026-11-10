from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from markupsafe import Markup, escape


class HaderMobileNotificationCampaign(models.Model):
    _name = "hader.mobile.notification.campaign"
    _inherit = ["mail.thread"]
    _description = "Mobile Notification Campaign"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    title = fields.Char(translate=True)
    body = fields.Text(translate=True)
    title_ar = fields.Char(string="Arabic Title")
    body_ar = fields.Text(string="Arabic Text")
    title_en = fields.Char(string="English Title")
    body_en = fields.Text(string="English Text")
    preview_ar = fields.Html(compute="_compute_previews", sanitize=False)
    preview_en = fields.Html(compute="_compute_previews", sanitize=False)
    image_url = fields.Char(string="Notification Image URL")
    scheduled_at = fields.Datetime(string="Scheduled At")
    audience = fields.Selection(
        [("all", "All mobile employees"), ("selected", "Selected employees")],
        required=True, default="all",
    )
    employee_ids = fields.Many2many("hr.employee", string="Employees")
    state = fields.Selection(
        [("draft", "Draft"), ("scheduled", "Scheduled"), ("sent", "Sent")],
        default="draft", required=True, readonly=True
    )
    inbox_ids = fields.One2many("hader.mobile.notification.inbox", "campaign_id", readonly=True)
    delivery_ids = fields.One2many("hader.mobile.push.delivery", "campaign_id", readonly=True)
    sent_at = fields.Datetime(readonly=True)
    recipient_count = fields.Integer(readonly=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    @api.depends("title_ar", "body_ar", "title_en", "body_en", "image_url")
    def _compute_previews(self):
        for campaign in self:
            campaign.preview_ar = campaign._preview_html("ar")
            campaign.preview_en = campaign._preview_html("en")

    def _preview_html(self, locale):
        self.ensure_one()
        title, body = self._localized_content(locale)
        direction = "rtl" if locale == "ar" else "ltr"
        image = ""
        if self.image_url:
            image = Markup('<img src="%s" style="width:100%%;max-height:140px;object-fit:cover;border-radius:10px;margin-top:10px"/>') % escape(self.image_url)
        return Markup(
            '<div dir="%s" style="max-width:310px;margin:8px auto;padding:18px;border-radius:28px;background:#171717;color:#fff;border:8px solid #333">'
            '<div style="font-size:11px;color:#bbb;margin-bottom:14px">Hader Employee • now</div>'
            '<div style="background:#2b2b2b;padding:13px;border-radius:13px">'
            '<strong style="display:block;font-size:15px">%s</strong>'
            '<span style="display:block;margin-top:5px;color:#ddd">%s</span>%s</div></div>'
        ) % (direction, escape(title), escape(body), image)

    def _localized_content(self, locale):
        self.ensure_one()
        if locale == "en":
            return (self.title_en or self.title_ar or self.title or "",
                    self.body_en or self.body_ar or self.body or "")
        return (self.title_ar or self.title_en or self.title or "",
                self.body_ar or self.body_en or self.body or "")

    LOCKED_FIELDS_AFTER_SEND = {
        "name",
        "title",
        "body",
        "title_ar",
        "body_ar",
        "title_en",
        "body_en",
        "image_url",
        "scheduled_at",
        "audience",
        "employee_ids",
        "company_id",
    }

    def write(self, vals):
        if self.LOCKED_FIELDS_AFTER_SEND.intersection(vals.keys()):
            for record in self:
                if record.state == "sent":
                    raise ValidationError(
                        _("لا يمكن تعديل محتوى أو إعدادات الإشعار بعد إرساله. / Cannot modify a notification campaign after it has been sent.")
                    )
        return super().write(vals)

    def action_send(self):
        Inbox = self.env["hader.mobile.notification.inbox"].sudo()
        Identity = self.env["hader.mobile.identity"].sudo()
        for campaign in self:
            if campaign.state != "draft":
                raise ValidationError(_("Only draft campaigns can be sent."))
            if not (campaign.title_ar or campaign.title_en or campaign.title):
                raise ValidationError(_("Enter a notification title in Arabic or English."))
            if not (campaign.body_ar or campaign.body_en or campaign.body):
                raise ValidationError(_("Enter notification text in Arabic or English."))
            if campaign.audience == "selected" and not campaign.employee_ids:
                raise ValidationError(_("Select at least one employee."))
            if campaign.scheduled_at and campaign.scheduled_at > fields.Datetime.now():
                campaign.state = "scheduled"
                campaign.message_post(
                    body=Markup(
                        "<div><strong>📅 تمت جدولة الإشعار / Notification Scheduled:</strong> %s</div>"
                    ) % escape(str(campaign.scheduled_at)),
                    subtype_xmlid="mail.mt_note",
                )
                continue
            campaign._send_now(Inbox, Identity)
        return True

    def _send_now(self, Inbox=None, Identity=None):
        Inbox = Inbox or self.env["hader.mobile.notification.inbox"].sudo()
        Identity = Identity or self.env["hader.mobile.identity"].sudo()
        for campaign in self:
            domain = [("active", "=", True), ("state", "=", "active"),
                      ("employee_id.company_id", "=", campaign.company_id.id)]
            if campaign.audience == "selected":
                if not campaign.employee_ids:
                    raise ValidationError(_("Select at least one employee."))
                domain.append(("employee_id", "in", campaign.employee_ids.ids))
            identities = Identity.search(domain)
            inboxes = Inbox.create([{
                "identity_id": identity.id,
                "title": campaign._localized_content("ar")[0],
                "body": campaign._localized_content("ar")[1],
                "title_ar": campaign._localized_content("ar")[0],
                "body_ar": campaign._localized_content("ar")[1],
                "title_en": campaign._localized_content("en")[0],
                "body_en": campaign._localized_content("en")[1],
                "image_url": campaign.image_url,
                "category": "announcement",
                "campaign_id": campaign.id,
            } for identity in identities])
            campaign.write({
                "state": "sent", "sent_at": fields.Datetime.now(),
                "recipient_count": len(identities),
            })
            inboxes._send_push()
            deliveries = inboxes.mapped("delivery_ids")
            accepted = len(deliveries.filtered(lambda d: d.state == "sent"))
            failed = len(deliveries.filtered(lambda d: d.state in ("failed", "unregistered")))
            pending = len(deliveries.filtered(lambda d: d.state == "pending"))
            no_device = len(inboxes.filtered(lambda i: not i.delivery_ids))
            summary = Markup(
                '<div style="line-height:1.8">'
                '<strong>✅ ملخص إرسال الحملة / Campaign Delivery Summary:</strong>'
                '<ul style="margin:6px 0 0 0;padding-inline-start:20px">'
                '<li>📥 <strong>إشعارات داخل التطبيق (In-App Inbox):</strong> %s</li>'
                '<li>🟢 <strong>تم القبول والإرسال عبر Firebase (Accepted by Firebase):</strong> %s</li>'
                '<li>🔴 <strong>فشل الإرسال أو جهاز غير مسجل (Failed / Unregistered):</strong> %s</li>'
                '<li>⏳ <strong>قيد الانتظار (Pending):</strong> %s</li>'
                '<li>📱 <strong>موظفون بدون جهاز مفعل للإشعارات (No Eligible Device):</strong> %s</li>'
                '</ul>'
                '<div style="font-size:12px;color:#666;margin-top:4px">'
                'يمكنك مراجعة تفاصيل كل جهاز من تبويب <strong>سجل إرسال الإشعارات (Push Delivery Log)</strong> أعلاه.'
                '</div></div>'
            ) % (len(inboxes), accepted, failed, pending, no_device)
            campaign.message_post(body=summary, subtype_xmlid="mail.mt_note")

    @api.model
    def _cron_send_scheduled(self):
        campaigns = self.search([
            ("state", "=", "scheduled"),
            ("scheduled_at", "<=", fields.Datetime.now()),
        ])
        campaigns._send_now()


class HaderMobileNotificationInbox(models.Model):
    _name = "hader.mobile.notification.inbox"
    _description = "Employee Mobile Notification"
    _order = "create_date desc, id desc"

    identity_id = fields.Many2one("hader.mobile.identity", required=True, index=True, ondelete="cascade")
    employee_id = fields.Many2one(related="identity_id.employee_id", store=True, index=True)
    company_id = fields.Many2one(related="identity_id.company_id", store=True, index=True)
    title = fields.Char(required=True)
    body = fields.Text(required=True)
    title_ar = fields.Char()
    body_ar = fields.Text()
    title_en = fields.Char()
    body_en = fields.Text()
    image_url = fields.Char()
    category = fields.Selection([
        ("announcement", "Announcement"),
        ("correction_submitted", "Correction submitted"),
        ("correction_result", "Correction result"),
        ("leave_submitted", "Time-off request submitted"),
        ("leave_result", "Time-off request result"),
        ("expense_submitted", "Expense request submitted"),
        ("expense_result", "Expense request result"),
        ("service_submitted", "Service request submitted"),
        ("service_result", "Service request result"),
    ], required=True, default="announcement", index=True)
    campaign_id = fields.Many2one("hader.mobile.notification.campaign", ondelete="set null")
    correction_id = fields.Many2one("hader.attendance.correction", ondelete="set null")
    is_read = fields.Boolean(default=False, index=True)
    read_at = fields.Datetime(readonly=True)
    delivery_ids = fields.One2many("hader.mobile.push.delivery", "inbox_id")

    def _send_push(self):
        Delivery = self.env["hader.mobile.push.delivery"].sudo()
        for inbox in self:
            Delivery.send_inbox(inbox)
        return True

    @api.model
    def notify_employee(self, employee, title, body, category, correction=None,
                        title_en=None, body_en=None):
        identity = self.env["hader.mobile.identity"].sudo().search([
            ("employee_id", "=", employee.id), ("active", "=", True), ("state", "=", "active")
        ], limit=1)
        if not identity:
            return self.browse()
        inbox = self.sudo().create({
            "identity_id": identity.id,
            "title": title,
            "body": body,
            "title_ar": title,
            "body_ar": body,
            "title_en": title_en or title,
            "body_en": body_en or body,
            "category": category,
            "correction_id": correction.id if correction else False,
        })
        inbox._send_push()
        return inbox

    def _localized_content(self, locale):
        self.ensure_one()
        if locale == "en":
            return self.title_en or self.title_ar or self.title, self.body_en or self.body_ar or self.body
        return self.title_ar or self.title_en or self.title, self.body_ar or self.body_en or self.body

    def mobile_dto(self, locale="ar"):
        self.ensure_one()
        title, body = self._localized_content(locale)
        return {
            "id": self.id,
            "title": title,
            "body": body,
            "category": self.category,
            "is_read": self.is_read,
            "created_at": self.create_date.isoformat() if self.create_date else None,
            "correction_ref": self.correction_id.id or None,
        }
