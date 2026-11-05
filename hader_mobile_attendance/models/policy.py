from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.base.models.res_partner import _tz_get


class HaderAttendancePolicy(models.Model):
    _name = "hader.attendance.policy"
    _description = "Hader Attendance Policy"
    _inherit = ["mail.thread", "mail.activity.mixin"]
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
        help="On site enforces an assigned geofence. Remote records the device location without a geofence. Hybrid allows on-site or remote punches. Field records the employee's actual field location.",
    )
    require_geofence = fields.Boolean(default=True)
    maximum_accuracy_m = fields.Float(required=True, default=300.0)
    allow_mobile_punch = fields.Boolean(default=True)
    timezone = fields.Selection(
        _tz_get,
        required=True,
        default=lambda self: self.env.user.tz or "Asia/Riyadh",
    )
    shift_start_hour = fields.Float(required=True, default=8.0)
    shift_end_hour = fields.Float(required=True, default=17.0)
    late_grace_minutes = fields.Integer(required=True, default=15)
    early_leave_grace_minutes = fields.Integer(required=True, default=15)
    biometric_provider = fields.Selection(
        [
            ("disabled", "Disabled (Location Only)"),
            ("face_or_alternative", "Face Verification / Exemption Alternative (بصمة الوجه أو التحقق البديل)"),
        ],
        required=True,
        default="face_or_alternative",
    )

    @api.onchange("attendance_mode")
    def _onchange_attendance_mode(self):
        if self.attendance_mode in ("remote", "field"):
            self.require_geofence = False

    @api.constrains("maximum_accuracy_m")
    def _check_accuracy(self):
        if any(record.maximum_accuracy_m <= 0 for record in self):
            raise ValidationError(_("Maximum accuracy must be positive."))

    @api.constrains(
        "shift_start_hour",
        "shift_end_hour",
        "late_grace_minutes",
        "early_leave_grace_minutes",
    )
    def _check_shift(self):
        for record in self:
            if not 0 <= record.shift_start_hour < 24 or not 0 <= record.shift_end_hour < 24:
                raise ValidationError(_("Shift hours must be between 00:00 and 23:59."))
            if record.shift_start_hour == record.shift_end_hour:
                raise ValidationError(_("Shift start and end cannot be equal."))
            if record.late_grace_minutes < 0 or record.early_leave_grace_minutes < 0:
                raise ValidationError(_("Shift grace minutes cannot be negative."))


class HaderEmployeeAttendanceAssignment(models.Model):
    _name = "hader.employee.attendance.assignment"
    _description = "Employee Attendance Assignment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="cascade")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    policy_id = fields.Many2one("hader.attendance.policy", required=True, ondelete="restrict")
    attendance_mode = fields.Selection(related="policy_id.attendance_mode", readonly=True)
    location_ids = fields.Many2many(
        "hader.work.location",
        "hader_attendance_assignment_location_rel",
        "assignment_id",
        "location_id",
        string="Eligible locations",
    )
    date_from = fields.Date(required=True, default=fields.Date.context_today, index=True)
    date_to = fields.Date(index=True)
    active = fields.Boolean(default=True)

    @api.onchange("policy_id")
    def _onchange_policy_id(self):
        if self.policy_id.attendance_mode in ("remote", "field"):
            self.location_ids = [(5, 0, 0)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            policy_id = vals.get("policy_id")
            if policy_id:
                policy = self.env["hader.attendance.policy"].browse(policy_id)
                if policy.attendance_mode in ("remote", "field"):
                    vals["location_ids"] = [(5, 0, 0)]
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        for record in self:
            if record.policy_id.attendance_mode in ("remote", "field") and record.location_ids:
                super(HaderEmployeeAttendanceAssignment, record).write({"location_ids": [(5, 0, 0)]})
        return res

    @api.constrains("employee_id", "policy_id", "location_ids", "date_from", "date_to")
    def _check_assignment(self):
        for record in self:
            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(_("Assignment end date cannot precede its start date."))
            if record.policy_id.company_id != record.company_id:
                raise ValidationError(_("Policy and employee must belong to the same company."))
            if any(location.company_id != record.company_id for location in record.location_ids):
                raise ValidationError(_("All work locations must belong to the employee company."))
            if record.policy_id.require_geofence and record.policy_id.attendance_mode in ("on_site", "hybrid") and not record.location_ids:
                raise ValidationError(_("A geofenced policy requires at least one work location."))
