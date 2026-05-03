from odoo import fields, models, api
from datetime import datetime, timedelta


class HrPayslipWorkDays(models.Model):
    _inherit = "hr.payslip.worked_days"

    paid_bool = fields.Boolean(default=False, string="Paid Cheek")
    advanced_amount = fields.Float()

    @api.depends('is_paid', 'is_credit_time', 'number_of_hours', 'payslip_id', 'contract_id.wage',
                 'payslip_id.sum_worked_hours')
    def _compute_amount(self):
        res = super(HrPayslipWorkDays, self)._compute_amount()
        for rec in self:
            if rec.paid_bool:
                rec.amount = rec.advanced_amount

        return res




class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    is_bool = fields.Boolean()
    state = fields.Selection(selection_add=[('send', 'sent') ,('submit', 'Submitted') , ('verify' , )])

    def action_payslip_sent(self):
        self.write({'state': 'send'})

    def action_payslip_submit(self):
        self.write({'state': 'submit'})

    def action_payslip_unpaid(self):
        pass

    def compute_sheet(self):
        res = super(HrPayslip, self).compute_sheet()
        for rec in self:
            rec._get_workday_lines()
        self.write({'state': 'draft'})
        return res

    def _get_workday_lines(self):
        year_month = []
        year_month_payslip = []
        super(HrPayslip, self)._get_workday_lines()
        for rec in self:
            self.ensure_one()
            year_month_payslip.append(f"{rec.date_from.year}-{rec.date_from.month:02d}")
            # rec.worked_days_line_ids = [(5, 0, 0)]
            salary_advanced_work_entry = self.env['hr.work.entry.type'].search([('code', '=', 'SALARYAD')])
            day_vacation_paid_work_entry = self.env['hr.work.entry.type'].search([('code', '=', 'VACATIONDPAID')])

            if salary_advanced_work_entry or day_vacation_paid_work_entry:
                existing_work_entry = rec.worked_days_line_ids.filtered(
                    lambda line: line.work_entry_type_id == salary_advanced_work_entry[0]
                )
                vacation_existing_work_entry = rec.worked_days_line_ids.filtered(
                    lambda line: line.work_entry_type_id == day_vacation_paid_work_entry[0]
                )
                salary = 0.0
                day = 0

                if self._get_salary_advanced():
                    for vac in self._get_salary_advanced():


                        for leave in vac.leave_ids:
                            months_in_leave = self.get_months_between(leave.request_date_from, leave.request_date_to)
                            year_month.append(months_in_leave)

                        flattened_year_month = [item for sublist in year_month for item in sublist]

                        if set(year_month_payslip).intersection(flattened_year_month):
                            day += vac.num_of_vacation
                        flattened_dates = [datetime.strptime(ym, "%Y-%m") for ym in flattened_year_month]
                        min_date = min(flattened_dates).strftime("%Y-%m")

                        if year_month_payslip == [min_date]:
                            salary += vac.allowance_advance_salary
                else:
                    pass

                if existing_work_entry and vacation_existing_work_entry:
                    existing_work_entry.write({
                        'advanced_amount': salary,
                    })

                    vacation_existing_work_entry.write({
                        'number_of_days': day,
                        'number_of_hours': day * rec.contract_id.resource_calendar_id.hours_per_day,
                    })
                else:
                    salary_advanced = [{
                        'name': "Advanced Salary",
                        'work_entry_type_id': salary_advanced_work_entry[0].id,
                        'sequence': 40,
                        'paid_bool': True,
                        'advanced_amount': salary,

                    }]

                    vacation_day = [{
                        'name': "Settlement Day",
                        'work_entry_type_id': day_vacation_paid_work_entry[0].id,
                        'sequence': 50,
                        'paid_bool': True,
                        'number_of_days': day,
                        'number_of_hours': day * rec.contract_id.resource_calendar_id.hours_per_day,

                    }]

                    worked_days_lines = salary_advanced + vacation_day
                    rec.worked_days_line_ids = [(0, 0, x) for x in worked_days_lines]




    def _get_salary_advanced(self):
        result = []
        year_month = []
        year_month_payslip = []
        date_leave = []
        for rec in self:
            year_month_payslip.append(f"{rec.date_from.year}-{rec.date_from.month:02d}")
            settlement = self.env['employee.vacation.settlement'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('state', 'not in', ['draft', 'submit'])
            ])
            for sett in settlement:
                for leave in sett.leave_ids:
                    months_in_leave = self.get_months_between(leave.request_date_from, leave.request_date_to)
                    year_month.append(months_in_leave)
                flattened_year_month = [item for sublist in year_month for item in sublist]
                if set(year_month_payslip).intersection(flattened_year_month):
                    result.append(sett)
        return result if result else False



    def get_months_between(self, start_date, end_date):
        months = []
        current_date = datetime(start_date.year, start_date.month, 1)
        end_date = datetime(end_date.year, end_date.month, 1)

        while current_date <= end_date:
            months.append(f"{current_date.year}-{current_date.month:02d}")
            if current_date.month == 12:
                current_date = datetime(current_date.year + 1, 1, 1)
            else:
                current_date = datetime(current_date.year, current_date.month + 1, 1)

        return months
