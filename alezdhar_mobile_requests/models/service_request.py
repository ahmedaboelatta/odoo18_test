from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlezdharMobileService(models.Model):
    _name = "alezdhar.mobile.service"
    _description = "Mobile Employee Service"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    description = fields.Text(translate=True)
    icon = fields.Selection([
        ("description", "Document"), ("payments", "Payments"),
        ("support", "Support"), ("more", "General"),
    ], default="more", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", index=True)
    allow_attachment = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_company_unique", "unique(code, company_id)",
         "Service code must be unique per company."),
    ]


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
    state = fields.Selection([
        ("submitted", "Submitted"), ("in_progress", "In Progress"),
        ("done", "Done"), ("rejected", "Rejected"),
    ], default="submitted", required=True, tracking=True, index=True)
    assigned_user_id = fields.Many2one("res.users", tracking=True)
    resolution = fields.Text(tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.name == _("New"):
                record.name = "SR-%05d" % record.id
        return records

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
