from odoo import fields, models, api
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.translate import _
from odoo.tools.misc import format_date


class HrLeave(models.Model):
    _inherit = "hr.leave"

    settlement = fields.Boolean(default=False)
    settlement_done = fields.Boolean(default=False)

    def action_validate_wizard(self):
        if self.settlement:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Handle Leave',
                'res_model': 'hr.leave.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_employee_id': self.employee_id.id,
                    'default_leave_id': self.id,
                    'default_date': self.date_from.date() if self.date_from else False,

                }
            }
        else:
            self.action_validate()



    @api.constrains('date_from', 'date_to', 'employee_id')
    def _check_date(self):
        if self.env.context.get('leave_skip_date_check', False):
            return

        all_employees = self.all_employee_ids
        all_leaves = self.search([
            ('date_from', '<', max(self.mapped('date_to'))),
            ('date_to', '>', min(self.mapped('date_from'))),
            ('employee_id', 'in', all_employees.ids),
            ('id', 'not in', self.ids),
            ('state', 'not in', ['cancel', 'refuse']),
        ])
        for holiday in self:
            domain = [
                ('date_from', '<', holiday.date_to),
                ('date_to', '>', holiday.date_from),
                ('id', '!=', holiday.id),
                ('state', 'not in', ['cancel', 'refuse']),
            ]

            employee_ids = (holiday.employee_id | holiday.employee_ids).ids
            search_domain = domain + [('employee_id', 'in', employee_ids)]
            conflicting_holidays = all_leaves.filtered_domain(search_domain)

            if conflicting_holidays:
                conflicting_holidays_list = []
                # Do not display the name of the employee if the conflicting holidays have an employee_id.user_id equivalent to the user id
                holidays_only_have_uid = bool(holiday.employee_id)
                holiday_states = dict(conflicting_holidays.fields_get(allfields=['state'])['state']['selection'])
                for conflicting_holiday in conflicting_holidays:
                    conflicting_holiday_data = {}
                    conflicting_holiday_data['employee_name'] = conflicting_holiday.employee_id.name
                    conflicting_holiday_data['date_from'] = format_date(self.env,
                                                                        min(conflicting_holiday.mapped('date_from')))
                    conflicting_holiday_data['date_to'] = format_date(self.env,
                                                                      min(conflicting_holiday.mapped('date_to')))
                    conflicting_holiday_data['state'] = holiday_states[conflicting_holiday.state]
                    if conflicting_holiday.employee_id.user_id.id != self.env.uid:
                        holidays_only_have_uid = False
                    if conflicting_holiday_data not in conflicting_holidays_list:
                        conflicting_holidays_list.append(conflicting_holiday_data)
                if not conflicting_holidays_list:
                    return
                conflicting_holidays_strings = []
                if holidays_only_have_uid:
                    for conflicting_holiday_data in conflicting_holidays_list:
                        conflicting_holidays_string = _('from %(date_from)s to %(date_to)s - %(state)s',
                                                        date_from=conflicting_holiday_data['date_from'],
                                                        date_to=conflicting_holiday_data['date_to'],
                                                        state=conflicting_holiday_data['state'])
                        conflicting_holidays_strings.append(conflicting_holidays_string)
                    raise ValidationError(_("""\
    You've already booked time off which overlaps with this period:
    %s
    Attempting to double-book your time off won't magically make your vacation 2x better!
    """,
                                            "\n".join(conflicting_holidays_strings)))
                for conflicting_holiday_data in conflicting_holidays_list:
                    conflicting_holidays_string = "\n" + _(
                        '%(employee_name)s - from %(date_from)s to %(date_to)s - %(state)s',
                        employee_name=conflicting_holiday_data['employee_name'],
                        date_from=conflicting_holiday_data['date_from'],
                        date_to=conflicting_holiday_data['date_to'],
                        state=conflicting_holiday_data['state'])
                    conflicting_holidays_strings.append(conflicting_holidays_string)
                if holiday.settlement:
                    print('continue')
                    continue
                else:
                    # raise ValidationError(_(
                    #     "An employee already booked time off which overlaps with this period:%s",
                    #     "".join(conflicting_holidays_strings)))
                    continue
