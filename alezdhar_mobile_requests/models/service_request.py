from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlezdharMobileService(models.Model):
    _name = "alezdhar.mobile.service"
    _description = "Mobile Employee Service"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True, tracking=True)
    code = fields.Char(required=True, index=True)
    description = fields.Text(translate=True, tracking=True)
    icon = fields.Selection([
        ("description", "Document"), ("payments", "Payments"),
        ("support", "Support"), ("more", "General"),
    ], default="more", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", index=True)
    allow_attachment = fields.Boolean(default=True)
    state = fields.Selection([
        ("draft", "Draft"), ("published", "Published"),
    ], default="published", required=True, tracking=True, index=True)
    service_type = fields.Selection([
        ("general", "General Request"), ("complaint", "Employee Complaint"),
    ], default="general", required=True, tracking=True, index=True)
    responsible_user_ids = fields.Many2many(
        "res.users", "alezdhar_service_responsible_user_rel",
        "service_id", "user_id", string="Responsible Users", tracking=True,
        domain="[('share', '=', False)]",
    )
    field_ids = fields.One2many("alezdhar.mobile.service.field", "service_id", string="Request Fields")

    _sql_constraints = [
        ("code_company_unique", "unique(code, company_id)",
         "Service code must be unique per company."),
    ]

    def action_publish(self):
        self.write({"state": "published"})

    def action_draft(self):
        self.write({"state": "draft"})


class AlezdharMobileServiceField(models.Model):
    _name = "alezdhar.mobile.service.field"
    _description = "Mobile Service Form Field"
    _order = "sequence, id"

    service_id = fields.Many2one("alezdhar.mobile.service", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    label = fields.Char(required=True, translate=True)
    key = fields.Char(required=True)
    field_type = fields.Selection([
        ("text", "Single-line text"), ("textarea", "Multi-line text"),
        ("radio", "Radio buttons"), ("select", "Dropdown list"),
    ], required=True, default="text")
    required = fields.Boolean(default=False)
    option_ids = fields.One2many("alezdhar.mobile.service.field.option", "field_id", string="Options")

    _sql_constraints = [("key_service_unique", "unique(service_id, key)", "Field key must be unique per service.")]


class AlezdharMobileServiceFieldOption(models.Model):
    _name = "alezdhar.mobile.service.field.option"
    _description = "Mobile Service Field Option"
    _order = "sequence, id"

    field_id = fields.Many2one("alezdhar.mobile.service.field", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    label = fields.Char(required=True, translate=True)
    value = fields.Char(required=True)


class AlezdharMobileServiceRequest(models.Model):
    _name = "alezdhar.mobile.service.request"
    _description = "Employee Service Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(default=lambda self: _("New"), readonly=True, tracking=True)
    service_id = fields.Many2one("alezdhar.mobile.service", required=True, ondelete="restrict", tracking=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict", tracking=True)
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    description = fields.Text(required=True)
    answers_json = fields.Json(default=dict, readonly=True)
    state = fields.Selection([
        ("submitted", "Submitted"), ("in_progress", "In Progress"),
        ("done", "Done"), ("rejected", "Rejected"),
    ], default="submitted", required=True, tracking=True, index=True)
    assigned_user_id = fields.Many2one("res.users", tracking=True)
    assigned_user_ids = fields.Many2many(
        "res.users", "alezdhar_request_assigned_user_rel",
        "request_id", "user_id", string="Assigned Users", tracking=True,
        domain="[('share', '=', False)]",
    )
    resolution = fields.Text(tracking=True)
    active = fields.Boolean(default=True, tracking=True)

    def write(self, vals):
        old_assignees = {record.id: record.assigned_user_id for record in self}
        old_user_ids = {record.id: set(record.assigned_user_ids.ids) for record in self}
        result = super().write(vals)
        if "assigned_user_id" in vals:
            Inbox = self.env["alezdhar.mobile.notification.inbox"] if "alezdhar.mobile.notification.inbox" in self.env else False
            for record in self:
                if record.assigned_user_id and record.assigned_user_id != old_assignees[record.id]:
                    record.activity_schedule("mail.mail_activity_data_todo", user_id=record.assigned_user_id.id,
                                             summary=_("New employee service request assigned"))
                    employee = record.assigned_user_id.employee_id
                    if Inbox and employee:
                        Inbox.notify_employee(employee, "تم تعيين طلب جديد لك",
                            f"تم تعيين الطلب {record.name} لك: {record.service_id.name}", "announcement",
                            title_en="A new request was assigned to you",
                            body_en=f"Request {record.name} was assigned to you: {record.service_id.name}")
        if "assigned_user_ids" in vals:
            for record in self:
                new_users = record.assigned_user_ids.filtered(
                    lambda user: user.id not in old_user_ids[record.id]
                )
                record._notify_assigned_users(new_users)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.name == _("New"):
                record.name = "SR-%05d" % record.id
            if not record.assigned_user_ids and record.service_id.responsible_user_ids:
                record.assigned_user_ids = record.service_id.responsible_user_ids
            record._notify_assigned_users(record.assigned_user_ids)
        return records

    def _notify_assigned_users(self, users):
        Inbox = self.env["alezdhar.mobile.notification.inbox"] if "alezdhar.mobile.notification.inbox" in self.env else False
        for record in self:
            for user in users:
                existing = self.env["mail.activity"].search_count([
                    ("res_model", "=", record._name), ("res_id", "=", record.id),
                    ("user_id", "=", user.id), ("activity_type_id", "=", self.env.ref("mail.mail_activity_data_todo").id),
                ])
                if not existing:
                    record.activity_schedule("mail.mail_activity_data_todo", user_id=user.id,
                                             summary=_("New employee service request assigned"))
                employee = user.employee_id
                if Inbox and employee:
                    Inbox.notify_employee(employee, "تم تعيين طلب جديد لك",
                        f"تم تعيين الطلب {record.name} لك: {record.service_id.name}", "announcement",
                        title_en="A new request was assigned to you",
                        body_en=f"Request {record.name} was assigned to you: {record.service_id.name}")

    def action_start(self):
        self.write({"state": "in_progress", "assigned_user_id": self.env.user.id})

    def action_done(self):
        if any(not row.resolution for row in self):
            raise ValidationError(_("Enter the resolution before completing the request."))
        self.write({"state": "done"})

    def action_reject(self):
        if any(not row.resolution for row in self):
            raise ValidationError(_("Enter the rejection reason."))
        self.write({"state": "rejected"})
