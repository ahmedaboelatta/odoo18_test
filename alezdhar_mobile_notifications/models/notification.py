from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlezdharMobileNotificationCampaign(models.Model):
    _name = "alezdhar.mobile.notification.campaign"
    _description = "Mobile Notification Campaign"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    title = fields.Char(required=True, translate=True)
    body = fields.Text(required=True, translate=True)
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
    sent_at = fields.Datetime(readonly=True)
    recipient_count = fields.Integer(readonly=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    def action_send(self):
        Inbox = self.env["alezdhar.mobile.notification.inbox"].sudo()
        Identity = self.env["alezdhar.mobile.identity"].sudo()
        for campaign in self:
            if campaign.state != "draft":
                raise ValidationError(_("Only draft campaigns can be sent."))
            if campaign.audience == "selected" and not campaign.employee_ids:
                raise ValidationError(_("Select at least one employee."))
            if campaign.scheduled_at and campaign.scheduled_at > fields.Datetime.now():
                campaign.state = "scheduled"
                continue
            campaign._send_now(Inbox, Identity)
        return True

    def _send_now(self, Inbox=None, Identity=None):
        Inbox = Inbox or self.env["alezdhar.mobile.notification.inbox"].sudo()
        Identity = Identity or self.env["alezdhar.mobile.identity"].sudo()
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
                "title": campaign.title,
                "body": campaign.body,
                "image_url": campaign.image_url,
                "category": "announcement",
                "campaign_id": campaign.id,
            } for identity in identities])
            campaign.write({
                "state": "sent", "sent_at": fields.Datetime.now(),
                "recipient_count": len(identities),
            })
            inboxes._send_push()

    @api.model
    def _cron_send_scheduled(self):
        campaigns = self.search([
            ("state", "=", "scheduled"),
            ("scheduled_at", "<=", fields.Datetime.now()),
        ])
        campaigns._send_now()


class AlezdharMobileNotificationInbox(models.Model):
    _name = "alezdhar.mobile.notification.inbox"
    _description = "Employee Mobile Notification"
    _order = "create_date desc, id desc"

    identity_id = fields.Many2one("alezdhar.mobile.identity", required=True, index=True, ondelete="cascade")
    employee_id = fields.Many2one(related="identity_id.employee_id", store=True, index=True)
    company_id = fields.Many2one(related="identity_id.company_id", store=True, index=True)
    title = fields.Char(required=True)
    body = fields.Text(required=True)
    image_url = fields.Char()
    category = fields.Selection([
        ("announcement", "Announcement"),
        ("correction_submitted", "Correction submitted"),
        ("correction_result", "Correction result"),
    ], required=True, default="announcement", index=True)
    campaign_id = fields.Many2one("alezdhar.mobile.notification.campaign", ondelete="set null")
    correction_id = fields.Many2one("alezdhar.attendance.correction", ondelete="set null")
    is_read = fields.Boolean(default=False, index=True)
    read_at = fields.Datetime(readonly=True)
    delivery_ids = fields.One2many("alezdhar.mobile.push.delivery", "inbox_id")

    def _send_push(self):
        Delivery = self.env["alezdhar.mobile.push.delivery"].sudo()
        for inbox in self:
            Delivery.send_inbox(inbox)
        return True

    @api.model
    def notify_employee(self, employee, title, body, category, correction=None):
        identity = self.env["alezdhar.mobile.identity"].sudo().search([
            ("employee_id", "=", employee.id), ("active", "=", True), ("state", "=", "active")
        ], limit=1)
        if not identity:
            return self.browse()
        inbox = self.sudo().create({
            "identity_id": identity.id,
            "title": title,
            "body": body,
            "category": category,
            "correction_id": correction.id if correction else False,
        })
        inbox._send_push()
        return inbox

    def mobile_dto(self):
        self.ensure_one()
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "category": self.category,
            "is_read": self.is_read,
            "created_at": self.create_date.isoformat() if self.create_date else None,
            "correction_ref": self.correction_id.id or None,
        }
