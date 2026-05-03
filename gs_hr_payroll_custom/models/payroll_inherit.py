# -*- coding: utf-8 -*-

from odoo import api, fields, models ,_
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_is_zero
from collections import defaultdict
from datetime import datetime, date, time
from dateutil.relativedelta import relativedelta
import pytz


from odoo.osv import expression
from odoo.tools import format_date


class GsHrPayslipEmployeesInherit(models.TransientModel):
    _inherit = 'hr.payslip.employees'

    # def compute_sheet(self):
    #     for rec in self.employee_ids:
    #         payslip_run = self.env['hr.payslip.run'].browse(self.env.context.get('active_id'))
    #         if rec.id and payslip_run.date_start and payslip_run.date_end:
    #             payslips = self.env['hr.payslip'].search([('employee_id', '=', rec.id)
    #                                                          ,('date_from', '=', payslip_run.date_start)
    #                                                          ,('date_to', '=', payslip_run.date_end)
    #                                                          ,('payment_state', '!=', 'refund')
    #                                                       ])
    #             if payslips:
    #                 raise ValidationError(_('This Employee (' + rec.name + ') ' + 'Already exists'))
    #     result = super(GsHrPayslipEmployeesInherit, self).compute_sheet()
    #     return result


    def compute_sheet(self):
        self.ensure_one()
        for rec in self.employee_ids:
            payslip_run = self.env['hr.payslip.run'].browse(self.env.context.get('active_id'))
            if rec.id and payslip_run.date_start and payslip_run.date_end:
                payslips = self.env['hr.payslip'].search([('employee_id', '=', rec.id)
                                                             ,('date_from', '=', payslip_run.date_start)
                                                             ,('date_to', '=', payslip_run.date_end)
                                                             ,('payment_state', '!=', 'refund')
                                                          ])
                if payslips:
                    raise ValidationError(_('This Employee (' + rec.name + ') ' + 'Already exists'))
        if not self.env.context.get('active_id'):
            from_date = fields.Date.to_date(self.env.context.get('default_date_start'))
            end_date = fields.Date.to_date(self.env.context.get('default_date_end'))
            today = fields.date.today()
            first_day = today + relativedelta(day=1)
            last_day = today + relativedelta(day=31)
            if from_date == first_day and end_date == last_day:
                batch_name = from_date.strftime('%B %Y')
            else:
                batch_name = _('From %(from_date)s to %(end_date)s', from_date=format_date(self.env, from_date), end_date=format_date(self.env, end_date))
            payslip_run = self.env['hr.payslip.run'].create({
                'name': batch_name,
                'date_start': from_date,
                'date_end': end_date,
            })
        else:
            payslip_run = self.env['hr.payslip.run'].browse(self.env.context.get('active_id'))

        employees = self.with_context(active_test=False).employee_ids
        if not employees:
            raise UserError(_("You must select employee(s) to generate payslip(s)."))

        #Prevent a payslip_run from having multiple payslips for the same employee
        employees -= payslip_run.slip_ids.employee_id
        success_result = {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run',
            'views': [[False, 'form']],
            'res_id': payslip_run.id,
        }
        if not employees:
            payslip_run.slip_ids.write({'state': 'verify'})
            payslip_run.state = 'verify'
            return success_result

        payslips = self.env['hr.payslip']
        Payslip = self.env['hr.payslip']

        contracts = employees._get_contracts(
            payslip_run.date_start, payslip_run.date_end, states=['open', 'close']
        ).filtered(lambda c: c.active)
        contracts.generate_work_entries(payslip_run.date_start, payslip_run.date_end)
        work_entries = self.env['hr.work.entry'].search([
            ('date_start', '<=', payslip_run.date_end + relativedelta(days=1)),
            ('date_stop', '>=', payslip_run.date_start + relativedelta(days=-1)),
            ('employee_id', 'in', employees.ids),
        ])
        for slip in payslip_run.slip_ids:
            slip_tz = pytz.timezone(slip.contract_id.resource_calendar_id.tz)
            utc = pytz.timezone('UTC')
            date_from = slip_tz.localize(datetime.combine(slip.date_from, time.min)).astimezone(utc).replace(tzinfo=None)
            date_to = slip_tz.localize(datetime.combine(slip.date_to, time.max)).astimezone(utc).replace(tzinfo=None)
            payslip_work_entries = work_entries.filtered_domain([
                ('contract_id', '=', slip.contract_id.id),
                ('date_stop', '<=', date_to),
                ('date_start', '>=', date_from),
            ])
            payslip_work_entries._check_undefined_slots(slip.date_from, slip.date_to)


        if(self.structure_id.type_id.default_struct_id == self.structure_id):
            work_entries = work_entries.filtered(lambda work_entry: work_entry.state != 'validated')
            if work_entries._check_if_error():
                work_entries_by_contract = defaultdict(lambda: self.env['hr.work.entry'])

                for work_entry in work_entries.filtered(lambda w: w.state == 'conflict'):
                    work_entries_by_contract[work_entry.contract_id] |= work_entry

                for contract, work_entries in work_entries_by_contract.items():
                    conflicts = work_entries._to_intervals()
                    time_intervals_str = "\n - ".join(['', *["%s -> %s (%s)" % (s[0], s[1], s[2].employee_id.name) for s in conflicts._items]])
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Some work entries could not be validated.'),
                        'message': _('Time intervals to look for:%s', time_intervals_str),
                        'sticky': False,
                    }
                }


        default_values = Payslip.default_get(Payslip.fields_get())
        payslips_vals = []
        for contract in self._filter_contracts(contracts):
            values = dict(default_values, **{
                'name': _('New Payslip'),
                'employee_id': contract.employee_id.id,
                'payslip_run_id': payslip_run.id,
                'date_from': payslip_run.date_start,
                'date_to': payslip_run.date_end,
                'contract_id': contract.id,
                'struct_id': self.structure_id.id or contract.struct_id.id,
            })
            payslips_vals.append(values)
        payslips = Payslip.with_context(tracking_disable=True).create(payslips_vals)
        payslips._compute_name()
        payslips.compute_sheet()
        payslip_run.slip_ids.write({'state': 'verify'})
        payslip_run.state = 'verify'

        return success_result


class GsHrContractInherit(models.Model):
    _inherit = 'hr.contract'

    struct_id = fields.Many2one('hr.payroll.structure', string="Structure")


class GsAccountMoveInherit(models.Model):
    _inherit = 'account.move'

    gs_payslip_ids = fields.Many2many('hr.payslip', string='Payslip')
    is_true = fields.Boolean(compute="_compute_is_true")

    def _compute_is_true(self):
        for rec in self:
            rec.is_true = False
            if rec.has_reconciled_entries:
                if self.gs_payslip_ids:
                    for payslip in self.gs_payslip_ids:
                        if payslip.payment_state == 'in_payment':
                            payslip.payment_state = 'paid'
                    rec.is_true = True


class GsAccountAccountInherit(models.Model):
    _inherit = 'account.account'

    is_payroll = fields.Boolean()


class GsHrPayslipInherit(models.Model):
    _inherit = 'hr.payslip'

    payment_state = fields.Selection(selection=[
        ('not_paid', 'Not Paid'),
        ('in_payment', 'In Payment'),
        ('paid', 'paid'),
        ('refund', 'Refund')
    ], string='Payment Status', required=True , default='not_paid')

    gs_account_id = fields.Many2one('account.account', string="Account")
    gs_journal_entries_id = fields.Many2one('account.move', string="Journal Entries")
    is_true = fields.Boolean(compute="_compute_is_true")
    registration_number2 = fields.Char('Number of the Employee', related='contract_id.employee_id.registration_number2')

    def _cron_state_payroll(self):
        payslips = self.env['hr.payslip'].search([('payment_state', '=', 'in_payment')])
        for payslip in payslips:
            if payslip.gs_journal_entries_id.has_reconciled_entries:
                payslip.payment_state = 'paid'

    def action_register_payment(self):
        res = super().action_register_payment()
        res['context'].update({
            'default_payslip_id': self.id,
        })
        return res
    def _compute_is_true(self):
        for rec in self:
            rec.is_true = False
            if rec.gs_journal_entries_id.has_reconciled_entries:
                if rec.gs_journal_entries_id.gs_payslip_ids:
                    for payslip in rec.gs_journal_entries_id.gs_payslip_ids:
                        if payslip.payment_state == 'in_payment':
                            payslip.payment_state = 'paid'
                    rec.is_true = True

    @api.onchange('employee_id', 'date_from', 'date_to')
    def unique_payslip(self):
        for rec in self:
            if rec.employee_id and rec.date_from and rec.date_to:
                payslips = self.env['hr.payslip'].search([('employee_id', '=', rec.employee_id.id)
                                                             ,('date_from', '=', rec.date_from)
                                                             ,('date_to', '=', rec.date_to)
                                                             ,('payment_state', '!=', 'refund')
                                                          ])
                if payslips:
                    raise ValidationError(_('This Employee (' + rec.employee_id.name + ') ' + 'Already exists'))

    def refund_sheet(self):
        self.payment_state = 'refund'
        result = super(GsHrPayslipInherit, self).refund_sheet()
        return result

    def _prepare_slip_lines(self, date, line_ids):
        self.ensure_one()
        precision = self.env['decimal.precision'].precision_get('Payroll')
        new_lines = []
        for line in self.line_ids.filtered(lambda line: line.category_id):
            amount = -line.total if self.credit_note else line.total
            if line.code == 'NET': # Check if the line is the 'Net Salary'.
                for tmp_line in self.line_ids.filtered(lambda line: line.category_id):
                    if tmp_line.salary_rule_id.not_computed_in_net: # Check if the rule must be computed in the 'Net Salary' or not.
                        if amount > 0:
                            amount -= abs(tmp_line.total)
                        elif amount < 0:
                            amount += abs(tmp_line.total)
            if float_is_zero(amount, precision_digits=precision):
                continue
            debit_account_id = line.salary_rule_id.account_debit.id
            credit_account_id = line.salary_rule_id.account_credit.id

            if debit_account_id: # If the rule has a debit account.
                debit = amount if amount > 0.0 else 0.0
                credit = -amount if amount < 0.0 else 0.0
                debit_line = self._prepare_line_values(line, debit_account_id, date, debit, credit)
                new_lines.append(debit_line)

            if credit_account_id: # If the rule has a credit account.
                debit = -amount if amount < 0.0 else 0.0
                credit = amount if amount > 0.0 else 0.0
                credit_line = self._prepare_line_values(line, credit_account_id, date, debit, credit)
                new_lines.append(credit_line)

        return new_lines

    def create_register_payment(self):
        return {
            'name': _('Register Payment'),
            'res_model': 'register.payment.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'context': self.env.context,
            'type': 'ir.actions.act_window',
        }

    def _prepare_line_values(self, line, account_id, date, debit, credit):
        # return {
        #     'name': line.name,
        #     'partner_id': line.slip_id.employee_id.address_home_id.id,
        #     'account_id': account_id,
        #     'journal_id': line.slip_id.struct_id.journal_id.id,
        #     'date': date,
        #     'debit': debit,
        #     'credit': credit,
        #     'analytic_distribution': (line.salary_rule_id.analytic_account_id and {
        #         line.salary_rule_id.analytic_account_id.id: 100}) or
        #                              (line.slip_id.contract_id.analytic_account_id.id and {
        #                                  line.slip_id.contract_id.analytic_account_id.id: 100}),        }
        res = super()._prepare_line_values( line, account_id, date, debit, credit)
        res.update({
            'partner_id': line.slip_id.employee_id.address_home_id.id,
        })
        return res

    def action_payslip_done(self):
        res = super(GsHrPayslipInherit, self).action_payslip_done()
        for rec in self:
            # if rec.move_id:
            #     rec.move_id.branch_id = rec.employee_id.branch_id.id
            for line in rec.line_ids:
                if line.code == 'NET':
                    if line.total < 0:
                        raise ValidationError(_('Total Salary Less Than Zero'))

        return res
    @api.onchange('struct_id')
    @api.constrains('struct_id')
    def _onchange_struct_id(self):
        self.input_line_ids = [(5,0,0)]
        inputs = []
        for record in self.struct_id.input_line_type_ids:
           inputs.append((0,0,{
               'input_type_id': record.id,
               'name':  record.name,
           }))
        self.input_line_ids = inputs
