from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlezdharMobileNotificationCampaign(models.Model):
    _name = "alezdhar.mobile.notification.campaign"
    _description = "Mobile Notification Campaign"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    title = fields.Char(required=True, translate=True)
    body = fields.Text(required=True, translate=True)
    audience = fields.Selection(
        [("all", "All mobile employees"), ("selected", "Selected employees")],
        required=True, default="all",
    )
    employee_ids = fields.Many2many("hr.employee", string="Employees")
    state = fields.Selection(
        [("draft", "Draft"), ("sent", "Sent")], default="draft", required=True, readonly=True
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
            domain = [("active", "=", True), ("state", "=", "active"),
                      ("employee_id.company_id", "=", campaign.company_id.id)]
            if campaign.audience == "selected":
                if not campaign.employee_ids:
                    raise ValidationError(_("Select at least one employee."))
                domain.append(("employee_id", "in", campaign.employee_ids.ids))
            identities = Identity.search(domain)
            Inbox.create([{
                "identity_id": identity.id,
                "title": campaign.title,
                "body": campaign.body,
                "category": "announcement",
                "campaign_id": campaign.id,
            } for identity in identities])
            campaign.write({
                "state": "sent", "sent_at": fields.Datetime.now(),
                "recipient_count": len(identities),
            })
        return True


class AlezdharMobileNotificationInbox(models.Model):
    _name = "alezdhar.mobile.notification.inbox"
    _description = "Employee Mobile Notification"
    _order = "create_date desc, id desc"

    identity_id = fields.Many2one("alezdhar.mobile.identity", required=True, index=True, ondelete="cascade")
    employee_id = fields.Many2one(related="identity_id.employee_id", store=True, index=True)
    company_id = fields.Many2one(related="identity_id.company_id", store=True, index=True)
    title = fields.Char(required=True)
    body = fields.Text(required=True)
    category = fields.Selection([
        ("announcement", "Announcement"),
        ("correction_submitted", "Correction submitted"),
        ("correction_result", "Correction result"),
    ], required=True, default="announcement", index=True)
    campaign_id = fields.Many2one("alezdhar.mobile.notification.campaign", ondelete="set null")
    correction_id = fields.Many2one("alezdhar.attendance.correction", ondelete="set null")
    is_read = fields.Boolean(default=False, index=True)
    read_at = fields.Datetime(readonly=True)

    @api.model
    def notify_employee(self, employee, title, body, category, correction=None):
        identity = self.env["alezdhar.mobile.identity"].sudo().search([
            ("employee_id", "=", employee.id), ("active", "=", True), ("state", "=", "active")
        ], limit=1)
        if not identity:
            return self.browse()
        return self.sudo().create({
            "identity_id": identity.id,
            "title": title,
            "body": body,
            "category": category,
            "correction_id": correction.id if correction else False,
        })

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
