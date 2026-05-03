from odoo import models, fields, api
from odoo.exceptions import ValidationError

class HrLeaveWizard(models.TransientModel):
    _name = 'hr.leave.wizard'
    _description = 'Wizard to Handle Leave Actions'

    employee_id = fields.Many2one('hr.employee', required=True, string="Employee")
    type = fields.Selection([
        ('re_lev', 'Return of Leave'),
        ('n_appo', 'New Appointment')
    ], string="Type", required=True, default='re_lev')
    date = fields.Date(string="Date", required=True)
    leave_id = fields.Many2one('hr.leave', domain="[('employee_id', '=', employee_id)]", string="Leave")

    @api.onchange('leave_id')
    def _onchange_leave_id(self):
        if self.leave_id:
            self.employee_id = self.leave_id.employee_id

    def action_confirm(self):
        self.leave_id.action_validate()
        for rec in self:
            if rec.type == 're_lev' and rec.leave_id:
                leave_start = rec.leave_id.date_from.date()
                leave_end = rec.leave_id.date_to.date()
                if rec.date < leave_start or rec.date > leave_end:
                    raise ValidationError(
                        "The return date must be within the leave period between {} and {}".format(
                            leave_start, leave_end
                        )
                    )
                else:
                    rec.leave_id.settlement_done = True
                    rec._update_work_entries()

    def _update_work_entries(self):
        for rec in self:
            if rec.leave_id:
                leave_start = rec.leave_id.date_from
                leave_end = rec.leave_id.date_to

                work_entries = self.env['hr.work.entry'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    '|',
                    '&', ('date_start', '>=', leave_start), ('date_start', '<=', leave_end),
                    '&', ('date_stop', '>=', leave_start), ('date_stop', '<=', leave_end)
                ])

                for work in work_entries:
                    if rec.date <= work.date_start.date():
                        work.work_entry_type_id = self.env.ref('hr_work_entry.work_entry_type_attendance')
