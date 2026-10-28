from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AlezdharAttendancePolicy(models.Model):
    _name = "alezdhar.attendance.policy"
    _description = "Alezdhar Attendance Policy"
    _order = "company_id, name"

    name = fields.Char(required=True, translate=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    active = fields.Boolean(default=True)
    attendance_mode = fields.Selection(
        [("on_site", "On site"), ("remote", "Remote"), ("hybrid", "Hybrid"), ("field", "Field")],
        required=True,
        default="on_site",
    )
    require_geofence = fields.Boolean(default=True)
    maximum_accuracy_m = fields.Float(required=True, default=75.0)
    allow_mobile_punch = fields.Boolean(default=True)
    biometric_provider = fields.Selection(
        [("disabled", "Disabled")], required=True, default="disabled", readonly=True
    )

    @api.constrains("maximum_accuracy_m")
    def _check_accuracy(self):
        if any(record.maximum_accuracy_m <= 0 for record in self):
            raise ValidationError(_("Maximum accuracy must be positive."))


class AlezdharEmployeeAttendanceAssignment(models.Model):
    _name = "alezdhar.employee.attendance.assignment"
    _description = "Employee Attendance Assignment"
    _order = "date_from desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="cascade")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    policy_id = fields.Many2one("alezdhar.attendance.policy", required=True, ondelete="restrict")
    location_ids = fields.Many2many(
        "alezdhar.work.location",
        "alezdhar_attendance_assignment_location_rel",
        "assignment_id",
        "location_id",
        string="Eligible locations",
    )
    date_from = fields.Date(required=True, default=fields.Date.context_today, index=True)
    date_to = fields.Date(index=True)
    active = fields.Boolean(default=True)

    @api.constrains("employee_id", "policy_id", "location_ids", "date_from", "date_to")
    def _check_assignment(self):
        for record in self:
            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(_("Assignment end date cannot precede its start date."))
            if record.policy_id.company_id != record.company_id:
                raise ValidationError(_("Policy and employee must belong to the same company."))
            if any(location.company_id != record.company_id for location in record.location_ids):
                raise ValidationError(_("All work locations must belong to the employee company."))
            if record.policy_id.require_geofence and not record.location_ids:
                raise ValidationError(_("A geofenced policy requires at least one work location."))
