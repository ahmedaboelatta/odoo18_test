# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, exceptions
from odoo.exceptions import UserError, AccessError, ValidationError
from odoo import tools, _
from odoo.addons.resource.models.utils import HOURS_PER_DAY
import warnings


class HREndServiceBenefits(models.Model):
    _name = 'hr.end.service.benefit'
    _description = 'Employee End Of Service Benefits'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    # @api.constrains('total_taken_amount', 'amount')
    # def _check_amounts(self):
    #     for record in self:
    #         diff = record.total_deserved_amount - record.total_taken_amount
    #         if diff < record.amount:
    #             raise ValidationError('Your have exceed the residual amount')

    @api.constrains('date')
    def unique_end_service_benefit_date_per_employee(self):
        """Constraint to prevent create 2 end service benefits at the same day for them same employee"""
        for record in self:
            if record.date:
                end_service_benefit_ids = self.env['hr.end.service.benefit'].search(
                    [('employee_id', '=', record.employee_id.id), ('date', '=', record.date),
                     ('state', 'not in', ['cancel'])])
                if len(end_service_benefit_ids) > 1:
                    raise ValidationError(_('Employee has another end service benefit that date'))

    # @api.constrains('total_deserved_amount')
    # def _check_total_deserved_amount(self):
    #     for record in self:
    #         if record.total_deserved_amount == 0:
    #             if not record.end_service_benefit_type_id.is_deserved:
    #                 raise ValidationError(record.end_service_benefit_type_id.zero_message)

    @api.onchange('end_service_benefit_type_id', 'employee_id', 'service_period', 'type', 'payment_type')
    def _onchange_total_deserved_amount_warning(self):
        for record in self:
            if not record.end_service_benefit_type_id:
                return

            if record.total_deserved_amount == 0:
                if not record.end_service_benefit_type_id.is_deserved:
                    return {
                        'warning': {
                            'title': "Warring",
                            'message': record.end_service_benefit_type_id.zero_message,
                        }
                    }

    def _default_employee(self):
        """:returns current logged in employee using configured employee"""
        return self.env.context.get('default_employee_id') or self.env['hr.employee'].search(
            [('user_id', '=', self.env.uid)], limit=1)

    @api.depends('hiring_date', 'date')
    def _compute_period(self):
        for record in self:
            if record.hiring_date:
                hiring_date = record.hiring_date
                period_days = relativedelta(record.date, hiring_date) + relativedelta(days=1)
                record.years = period_days.years
                record.months = period_days.months
                record.days = period_days.days
                period = period_days.years + (period_days.months / 12.0) + (period_days.days / 365.0)
                record.service_period = period

    @api.depends('employee_id', 'service_period', 'end_service_benefit_type_id', 'date',
                 'total_holiday_deserved_amount', 'type', 'payment_type', 'other_amount',
                 'employee_id.contract_id.eos_total_amount')
    def _compute_total_deserved_amount(self):
        for record in self:
            # if record.payment_type == 'wage_allowance' and record.end_service_benefit_type_id and record.type == 'ending_service':
            #     record.total_deserved_amount = record.employee_id.contract_id.eos_total_amount
            #     continue
            contract_id = self.env['hr.contract'].search(
                [('employee_id', '=', record.employee_id.id)],
                limit=1, order='id desc')
            if contract_id:
                # wage = contract_id.wage
                # food = contract_id.food_allowance_val
                # trans = contract_id.trans_allowance_val
                # house = contract_id.house_allowance_val
                allowances = 0
                total_salary = contract_id.total_package_val
                if record.end_service_benefit_type_id.is_deserved == False:
                    if record.payment_type == 'wage_allowance':
                        allowances = sum(contract_id.contract_allowances.mapped('amount'))
                    total = 0.0
                    service_period = record.years + (record.months / 12.0) + (record.days / 365.0)
                    if service_period < 5:
                        equivalent = service_period * (0.5 * total_salary)
                        total += equivalent
                    else:
                        equivalent = (5 * (0.5 * total_salary)) + ((service_period - 5) * total_salary)
                        total += equivalent
                else:
                    total = 0.0
                # if record.end_service_benefit_type_id.deserved_after <= service_period:
                #     residual = service_period
                #     total_taken_years = 0
                #     for line in record.end_service_benefit_type_id.line_ids:
                #         if residual > line.deserved_for - total_taken_years:
                #             total += line.deserved_months * (line.deserved_for - total_taken_years) * (
                #                     wage + allowances + food + trans + house)
                #             total_taken_years = line.deserved_for
                #             residual = service_period - line.deserved_for
                #         else:
                #             total += line.deserved_months * residual * (wage + allowances + food + trans + house)
                #             total_taken_years += residual
                #             residual = 0.0
                # other_amount = record.other_amount if record.type == 'ending_service' else 0
                # record.total_deserved_amount = total + (record.total_holiday_deserved_amount or 0) + other_amount
                record.total_deserved_amount = total
                if record.end_service_benefit_type_id.resignation_request:
                    if service_period < 2:
                        record.total_deserved_amount = 0.0
                    elif 2 < service_period < 5:
                        equivalent = (service_period * (0.5 * total_salary)) * (1 / 3)
                        record.total_deserved_amount = equivalent
                    elif 5 < service_period < 9:
                        equivalent = ((5 * (0.5 * total_salary)) + ((service_period - 5) * total_salary)) * (2 / 3)
                        record.total_deserved_amount = equivalent
                    elif service_period > 10:
                        equivalent = (5 * (0.5 * total_salary)) + ((service_period - 5) * total_salary)
                        record.total_deserved_amount = equivalent
                    else:
                        record.total_deserved_amount = 0.0
                    # service_period = record.years + (record.months / 12.0) + (record.days / 365.0)
                    # for line in record.end_service_benefit_type_id.line_ids:
                    #     if service_period < line.deserved_for:
                    #         record.total_deserved_amount = line.percentage_amount
                    #         break

    @api.depends('employee_id', 'holiday_line_ids', 'holiday_line_ids.holiday_id', 'holiday_line_ids.remaining_leaves',
                 'holiday_line_ids.pay', 'type', 'payment_type')
    def _compute_total_holiday_deserved_amount(self):
        for record in self:
            total = 0.0
            if record.type == 'ending_service' or record.type == 'replacement':
                contract_id = self.env['hr.contract'].search(
                    [('employee_id', '=', record.employee_id.id)],
                    limit=1, order='id desc')
                if contract_id:
                    wage = contract_id.wage
                    food = contract_id.food_allowance_val
                    trans = contract_id.trans_allowance_val
                    house = contract_id.house_allowance_val
                    allowances = 0
                    if record.payment_type == 'wage_allowance' and contract_id.contract_allowances:
                        allowances = sum(contract_id.contract_allowances.mapped('amount'))
                        # print("bbbbbbbbbbbb" ,allowances )
                    total = 0.0
                    for line in record.holiday_line_ids:
                        if line.pay:
                            total += line.remaining_leaves * ((wage + allowances + food + trans + house) / 30)
                            print("total", total)
            record.total_holiday_deserved_amount = total

    @api.depends('employee_id', 'payslip_ids', 'payslip_ids.line_ids')
    def _compute_total_payslip_deserved_amount(self):
        payslip_total = 0
        for record in self:
            payslip_total += sum(
                line.total for line in record.payslip_ids.line_ids
                if line.salary_rule_id.code == 'NET'
            )
            record.total_payslip_deserved_amount = payslip_total

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            payslips = self.env['hr.payslip'].search([
                ('state', '=', 'done'),
                ('employee_id', '=', self.employee_id.id)
            ])
            self.payslip_ids = payslips

    @api.depends('employee_id')
    def _compute_total_taken_amount(self):
        for record in self:
            benefits_ids = self.env['hr.end.service.benefit'].search([
                ('employee_id', '=', record.employee_id.id),
                ('state', 'in', ['validated', 'paid']),
            ])
            sum = 0
            for benefits_id in benefits_ids:
                sum += benefits_id.amount
            record.total_taken_amount = sum

    @api.depends('total_deserved_amount', 'total_taken_amount')
    def _compute_available_amount(self):
        for record in self:
            record.available_amount = record.total_deserved_amount - record.total_taken_amount

    @api.depends('state')
    def _compute_payment_button_invisible(self):
        for record in self:
            record.payment_button_invisible = True
            if record.state != 'validated':
                record.payment_button_invisible = False
            if record.payment_id:
                record.payment_button_invisible = False

    @api.depends('total_deserved_amount', 'total_payslip_deserved_amount', 'total_holiday_deserved_amount',
                 'last_month_worked', 'other_allowance')
    def _compute_total_reward(self):
        for record in self:
            record.total_reward = record.total_deserved_amount + record.total_payslip_deserved_amount + record.total_holiday_deserved_amount + record.last_month_worked + record.other_allowance

    name = fields.Char(string='Reference', copy=False, default=_('New'),
                       tracking=True)
    # state = fields.Selection(string="State", tracking=True,
    #                          selection=[('draft', 'Draft'),
    #                                     ('confirmed', 'Confirmed'),
    #                                     ('validated', 'Validated'),
    #                                     ('paid', 'Paid'),
    #                                     ('cancel', 'Cancelled'), ],
    #                          default='draft', copy=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('approve', 'Approved'),
        ('pay_progress', 'Payment in progress'),
        ('journal_draft', 'Journal Entry Draft'),
        ('post', 'Posted'),
        ('done', 'Done'),
        ('paid', 'Payed'),
        ('refuse', 'Refused'),
        ('cancel', 'Canceled'),
    ], string="State", default='draft', track_visibility='onchange', copy=False)
    employee_id = fields.Many2one('hr.employee', string='Employee', index=True, readonly=True,
                                  states={'draft': [('readonly', False)], 'confirm': [('readonly', False)]},
                                  tracking=True)
    registration_number2 = fields.Char(related='employee_id.registration_number2', store=True, string='Employee Code')
    department_id = fields.Many2one(comodel_name="hr.department", string="Department",
                                    related='employee_id.department_id', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.user.company_id.currency_id)
    date = fields.Date(string="Date", default=datetime.now().strftime('%Y-%m-%d'), tracking=True,
                       copy=False)
    type = fields.Selection(string="Indemnity",
                            selection=[('replacement', 'Replacement'), ('ending_service', 'Ending Service'), ],
                            default='ending_service', )
    payment_type = fields.Selection(string="Payment Type",
                                    selection=[('wage', 'Wage'), ('wage_allowance', 'Wage + Allowances'), ],
                                    default='wage_allowance', required=True)
    end_service_benefit_type_id = fields.Many2one(comodel_name="hr.end.service.benefit.type", string="ES Reason", )
    hiring_date = fields.Date(string="Hiring Date", related='employee_id.hiring_date', store=True)
    years = fields.Integer(string="Years", compute=_compute_period, store=True)
    months = fields.Integer(string="Months", compute=_compute_period, store=True)
    days = fields.Integer(string="Days", compute=_compute_period, store=True)
    service_period = fields.Float(string="Service Period In Years", compute=_compute_period, store=True)
    notes = fields.Text(string="Notes", tracking=True)
    company_id = fields.Many2one('res.company', string='Company', related='employee_id.company_id', store=True)
    total_holiday_deserved_amount = fields.Float(string="Vacation Balance Amount",
                                                 compute=_compute_total_holiday_deserved_amount, store=True)
    total_payslip_deserved_amount = fields.Float(string="Salary Accrual",
                                                 compute=_compute_total_payslip_deserved_amount, store=True)
    last_month_worked = fields.Float('Last Month Worked Days Amount', compute='_compute_last_month_worked', store=True)
    other_amount = fields.Float(string="Other Amount")
    total_deserved_amount = fields.Float(string="ESR Indemnity", compute=_compute_total_deserved_amount,
                                         store=True)
    total_taken_amount = fields.Float(string="Previously ESR Disbursed Amount", compute=_compute_total_taken_amount,
                                      store=True)
    available_amount = fields.Float(string="Available to Disbursed", compute=_compute_available_amount, store=True)
    deduction_loan = fields.Float(compute='_compute_deduction_loan')
    other_deduction = fields.Float(compute='_compute_other_deduction')
    other_allowance = fields.Float(compute='_compute_other_allowance')
    amount = fields.Float(string="Total Entitlement", required=False, compute='_compute_amount')
    payment_id = fields.Many2one(comodel_name="account.payment", string="Reward Payment", copy=False, )
    payslip_payment_id = fields.Many2one(comodel_name="account.payment", string="Payslip Payment", copy=False, )
    account_move_id = fields.Many2one(comodel_name="account.move", string="Expense entry", copy=False, )
    payment_button_invisible = fields.Boolean(compute=_compute_payment_button_invisible)
    holiday_line_ids = fields.One2many('hr.end.benefit.holiday.line', 'reward_id', string="Holiday Lines",
                                       compute="_compute_holiday_lines", store=True)
    payslip_id = fields.Many2one(comodel_name="hr.payslip", string="Payslip")
    paid_status = fields.Selection([
        ('paid', 'Paid'),
        ('partial', 'Partial Paid'),
        ('not_paid', 'Not Paid')
    ], default='not_paid')

    payslip_ids = fields.Many2many(
        comodel_name="hr.payslip", string="Payslips",
        domain="[('state', '=', 'done'), ('employee_id', '=', employee_id)]",
        options="{'no_create': True}",
        readonly="state != 'draft'"
    )
    days_number = fields.Float(string="Last Month Worked Days Number", default=0)
    total_reward = fields.Float(string="Total Earning", compute=_compute_total_reward, store=True)

    vacation_settlement_id = fields.Many2one(
        'employee.vacation.settlement',
        string="Vacation Settlement"
    )
    total_net_payslip = fields.Float(string="Total Net Payslip", compute='_compute_total_net_payslip', store=True)
    analytic_account_id = fields.Many2one('account.analytic.account', compute='_compute_analytic', store=True,
                                          precompute=True)

    @api.depends('employee_id')
    def _compute_analytic(self):
        for record in self:
            if record.employee_id:
                contract = self.env['hr.contract'].search([('employee_id', '=', record.employee_id.id)])
                if contract:
                    record.analytic_account_id = contract.analytic_account_id
                else:
                    record.analytic_account_id = False

    @api.depends('payslip_ids')
    def _compute_total_net_payslip(self):
        for rec in self:
            total_net = 0.0
            if rec.payslip_ids:
                for payslip in rec.payslip_ids:
                    total_net += payslip.net_wage
                rec.total_net_payslip = total_net
            else:
                rec.total_net_payslip = 0.0

    @api.depends('employee_id', 'days_number')
    def _compute_last_month_worked(self):
        for record in self:
            total = 0.0

            contract_id = self.env['hr.contract'].search(
                [('employee_id', '=', record.employee_id.id), ('state', '=', 'open')],
                limit=1, order='id desc')
            if contract_id:
                wage = contract_id.wage
                food = contract_id.food_allowance_val
                trans = contract_id.trans_allowance_val
                house = contract_id.house_allowance_val
                allowances = contract_id.other_allowance_val
                total += record.days_number * ((wage + allowances + food + trans + house) / 30)
                print("totalllllllllllllllll", total)
            record.last_month_worked = total

    @api.depends('allows_ids', 'allows_ids.other_allowances')
    def _compute_other_allowance(self):
        for rec in self:
            rec.other_allowance = sum(rec.allows_ids.mapped('other_allowances'))

    @api.depends('employee_id')
    def _compute_deduction_loan(self):
        print("sssssssssssssssssssssssss")
        for record in self:
            if not record.employee_id:
                record.deduction_loan = 0.0
                continue

            employee_loans = self.env['employee.loan'].search([
                ('employee_id', '=', record.employee_id.id),
            ])

            total_deduction = sum(employee_loans.mapped(
                'installment_lines'
            ).filtered(lambda line: not line.payslip_id.name).mapped('installment_amt'))

            record.deduction_loan = total_deduction

    @api.depends('deduct_ids', 'deduct_ids.detuction')
    def _compute_other_deduction(self):
        for rec in self:
            rec.other_deduction = sum(rec.deduct_ids.mapped('detuction'))

    @api.depends('deduction_loan', 'other_deduction', 'total_reward')
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.total_reward - rec.other_deduction

    # @api.onchange('employee_id', 'type')
    # def _onchange_employee_id(self):
    #
    #     if self.type == 'ending_service':
    #         allocation_ids = self.env['hr.leave.allocation'].search(
    #             [('employee_id', '=', self.employee_id.id),
    #              ('state', 'not in', ['draft', 'cancel', 'refuse'])])
    #
    #         holiday_status_ids = allocation_ids and allocation_ids.mapped('holiday_status_id')
    #
    #         for line in self.holiday_line_ids:
    #
    #             line.unlink()
    #         lines_ids = []
    #         employee = self.employee_id and self.employee_id or False
    #         if employee:
    #             employee_record = self.env['hr.employee'].browse([employee.id])
    #             for holiday_status_id in holiday_status_ids:
    #                 data_days = holiday_status_id.get_allocation_data(employee_record)[employee.id]
    #                 remaining_leaves = 0
    #                 if isinstance(data_days, dict):
    #                     for holiday_status in holiday_status_id:
    #                         print("aaaaaaaaaaaaaaaaaaaa")
    #                         result = data_days.get(holiday_status.id, {})
    #                         remaining_leaves = result.get('remaining_leaves', 0)
    #                         if holiday_status_id.request_unit == 'hour':
    #                             remaining_leaves = remaining_leaves / (
    #                                     employee.company_id.number_of_hours_per_day or 8)
    #                             print('ddddddddddddddddddddd' ,remaining_leaves )
    #                         elif holiday_status_id.request_unit == 'half_day':
    #                             remaining_leaves = remaining_leaves / 2
    #                             print("bbbbbbbbbbbbbbbbbbbbbbbbbbb" ,remaining_leaves )
    #                 else:
    #                     remaining_leaves = 0
    #                     print("tttttttttttttttt" ,remaining_leaves )
    #                 lines_ids.append((0, 0, {'holiday_id': holiday_status_id.id,
    #                                          'remaining_leaves': remaining_leaves}))
    #         self.holiday_line_ids = lines_ids

    @api.depends('employee_id', 'type')
    def _compute_holiday_lines(self):
        for record in self:
            if record.type == 'ending_service' or record.type == 'replacement':
                record.holiday_line_ids = [(5, 0, 0)]  # 🔥 Clear existing lines

                allocation_ids = self.env['hr.leave.allocation'].search([
                    ('employee_id', '=', record.employee_id.id),
                    ('state', 'not in', ['draft', 'cancel', 'refuse'])
                ])

                holiday_status_ids = allocation_ids.mapped('holiday_status_id')
                employee = record.employee_id
                lines_ids = []

                if employee and holiday_status_ids:
                    employee_record = self.env['hr.employee'].browse(employee.id)
                    allocation_data = holiday_status_ids.get_allocation_data(employee_record)

                    if allocation_data and employee in allocation_data:
                        for data_tuple in allocation_data[employee]:
                            holiday_name, leave_data, _, holiday_status_id = data_tuple
                            remaining_leaves = leave_data.get('remaining_leaves', 0)

                            # ✅ Convert Units if Needed
                            holiday_status = self.env['hr.leave.type'].browse(holiday_status_id)
                            if holiday_status.request_unit == 'hour':
                                remaining_leaves /= (employee.company_id.number_of_hours_per_day or 8)
                            elif holiday_status.request_unit == 'half_day':
                                remaining_leaves /= 2

                            lines_ids.append((0, 0, {
                                'holiday_id': holiday_status_id,
                                'remaining_leaves': remaining_leaves,
                                'reward_id': record.id,  # Ensure One2many relation is set
                            }))

                record.holiday_line_ids = lines_ids

    def unlink(self):
        for record in self:
            if record.state != 'draft':
                raise ValidationError(_('You can only delete draft end service benefits'))
        res = super(HREndServiceBenefits, self).unlink()
        return res

    def create(self, vals):
        res = super().create(vals)
        for record in res:
            # Set the sequence safely AFTER record creation
            if record.name == _('New'):
                record.name = self.env['ir.sequence'].next_by_code('hr.end.service.benefit') or _('New')
            # Update vacation settlement
            vacation_settlement = self.env['employee.vacation.settlement'].search(
                [('employee_id', '=', record.employee_id.id)], limit=1)
            # if vacation_settlement:
            #     vacation_settlement.vacation_source = record.name
        return res

    # def action_submit(self):
    #     for record in self:
    #         group_manager = self.env.ref('hr.group_hr_manager')
    #         recipient_partners = []
    #         mail_server = self.env['ir.mail_server'].sudo().search([], order="sequence asc", limit=1)
    #         for recipient in group_manager[0].users:
    #             recipient_partners.append(
    #                 (4, recipient.partner_id.id)
    #             )
    #         template = False
    #         if recipient_partners and mail_server:
    #             template = self.env['ir.model.data'].get_object('hr_end_service_benefits',
    #                                                             'email_es_request_submission')
    #
    #         if template:
    #             mail_template = self.env['mail.template'].browse(template.id)
    #             mail_id = mail_template.send_mail(record.id)
    #             mail = self.env['mail.mail'].browse([mail_id])
    #             mail.recipient_ids = recipient_partners
    #         if record.amount <= 0:
    #             raise ValidationError(_('You can not confirm rewards with amount of zero'))
    #         SequenceObj = self.env['ir.sequence']
    #         number = SequenceObj.next_by_code('hr.end.service.benefit')
    #         record.name = number
    #         vacation_settlement = self.env['employee.vacation.settlement'].search(
    #             [('employee_id', '=', record.employee_id.id) , ('vacation_end_service' , '=' , True)], limit=1)
    #         if vacation_settlement:
    #             vacation_settlement.vacation_source = record.name
    #
    #
    #     record.write({'state': 'confirmed', 'name': number})

    # def action_validate(self):
    #     for record in self:
    #         group_manager = self.env.ref('account.group_account_manager')
    #         recipient_partners = []
    #         mail_server = self.env['ir.mail_server'].sudo().search([], order="sequence asc", limit=1)
    #         for recipient in group_manager[0].users:
    #             recipient_partners.append(
    #                 (4, recipient.partner_id.id)
    #             )
    #         template = False
    #         if recipient_partners and mail_server:
    #             template = self.env['ir.model.data'].get_object('hr_end_service_benefits',
    #                                                             'email_es_request_payment_request')
    #         if template:
    #             mail_template = self.env['mail.template'].browse(template.id)
    #             mail_id = mail_template.send_mail(record.id)
    #             mail = self.env['mail.mail'].browse([mail_id])
    #             mail.recipient_ids = recipient_partners
    #
    #         record.write({'state': 'validated'})
    #         if record.type == 'ending_service' or record.type == 'replacement':
    #             record.employee_id.toggle_active()
    #             contract_ids = self.env['hr.contract'].search(
    #                 [('employee_id', '=', record.employee_id.id), ('state', '=', 'open')],
    #                 order='id desc')
    #             for contract_id in contract_ids:
    #                 contract_id.state = 'cancel'

    def action_draft(self):
        for record in self:
            record.write({'state': 'draft'})
            if record.payment_id:
                record.payment_id.action_draft()
    def action_cancel(self):
        for record in self:
            record.write({'state': 'cancel'})

            AccountMove = self.env['account.move'].search([('id', '=', self.account_move_id.id)])
            if AccountMove:
                AccountMove.button_draft()
                AccountMove.button_cancel()
                AccountMove.unlink()
            payments = self.env['account.payment'].search([('memo', '=', self.name)])
            if payments:
                for rec in payments:
                    rec.action_cancel()
                    rec.unlink()
            record.paid_status = 'not_paid'

    def action_sheet_move_create(self):
        for rec in self:
            # Access the hr.benefit.settlement record related to the current hr.end.service.benefit record
            settlement = self.env['hr.benefit.settlement'].search([('request_id', '=', rec.id)], limit=1)

            if settlement and settlement.request_id.account_move_id and settlement.request_id.account_move_id.state == 'draft':
                # Post the draft journal entry
                settlement.request_id.account_move_id.action_post()
                rec.write({'state': 'post'})

                # Post a message for the current record
                rec.message_post(body=_("Journal entry has been successfully posted."))
                print("Draft journal entry has been posted.")
            else:
                raise exceptions.ValidationError(
                    _("No draft journal entry found or the entry is already posted. Please create the draft entry first.")
                )

    account_id = fields.Many2one(
        'account.account',
        string='Account',
        help="An expense account is expected"
    )

    # @api.depends('company_id')
    # def _compute_account_id(self):
    #     for record in self:
    #         if not record.account_id:
    #             record.account_id = self.env['account.account'].search([
    #                 ('company_id', '=', record.company_id.id)
    #             ], limit=1)

    @api.model
    def _default_journal_id(self):
        """ The journal is determining the company of the accounting entries generated from expense. We need to force journal company and expense sheet company to be the same. """
        journal = self.env['account.journal'].search([('is_vacation', '=', True)], limit=1)
        return journal.id

    journal_id = fields.Many2one('account.journal', string='vacation Journal', domain="[('is_vacation', '=', True)]",
                                 default=_default_journal_id, help="The journal used when the expense is done.")

    def action_sheet_move_create_draft(self):
        for rec in self:
            # Pass the necessary data to the wizard (without storing the Many2one reference)
            wizard = self.env['hr.benefit.settlement'].create({
                'request_id': rec.id,
            })
            wizard.settle_employee_reward_emp()
            rec.write({'state': 'journal_draft'})
            print("Settlement processed successfully")

    def action_reset_to_draft(self):
        return self.write({'state': 'draft'})

    def action_refuse(self):
        return self.write({'state': 'refuse'})

    def action_submit(self):
        self.write({'state': 'submit'})

    # def action_cancel(self):
    #     self.write({'state': 'cancel'})

    def action_approve(self):
        self.write({'state': 'approve'})

    def action_payment_in_progress(self):
        self.write({'state': 'pay_progress'})

    def action_register_payment(self):
        ''' Open the account.payment.register wizard to pay the selected journal entries.
        There can be more than one bank_account_id in the expense sheet when registering payment for multiple expenses.
        The default_partner_bank_id is set only if there is one available, if more than one the field is left empty.
        :return: An action opening the account.payment.register wizard.
        '''
        AccountMove = self.env['account.move'].search([('ref', '=', self.name)], limit=1)

        # self.write({'state': 'paid'})
        return {
            'name': _('Register Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'context': {
                'active_model': 'account.move',
                'active_ids': self.account_move_id.ids,
                'default_partner_bank_id': self.employee_id.sudo().bank_account_id.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',

        }

    def action_open_account_move(self):
        self.ensure_one()

        # Find the settlement record related to the current record
        settlement_record = self.env['hr.benefit.settlement'].search([('request_id', '=', self.id)], limit=1)
        payment_move = self.env['account.move'].search([('ref', '=', self.name)])

        if settlement_record:
            AccountMove = self.account_move_id
            return {
                'name': AccountMove.name,
                'type': 'ir.actions.act_window',
                'view_mode': 'list,form',
                # 'views': [[False, "form"]],
                'res_model': 'account.move',
                # 'res_id': AccountMove.id,
                'domain': ['|', ('id', 'in', AccountMove.ids), ('id', 'in', payment_move.ids)],
            }
        else:
            raise exceptions.UserError(_("No journal entry is linked to this record."))

    def set_allowance(self):
        allowance = self.env['type.allowances'].search([('type', '=', 'allwances')])
        allowances = []
        for record in allowance:
            allowances.append((0, 0, {
                'type_allowances': record.id,
                'service_id': self.id,

            }))
        return allowances

    def set_deduction(self):
        deduction = self.env['type.allowances'].search([('type', '=', 'deduction')])
        deductions = []
        for record in deduction:
            deductions.append((0, 0, {
                'type_detuction': record.id,
                'service_id': self.id,

            }))
        return deductions

    allows_ids = fields.One2many(comodel_name='employee.vacation.settlement.allowance', inverse_name='service_id',
                                 string="Allowances", store=True, default=lambda self: self.set_allowance())
    deduct_ids = fields.One2many(comodel_name='employee.vacation.settlement.detuction', inverse_name='service_id',
                                 string="Deduction", store=True, default=lambda self: self.set_deduction())


class EmployeeVacationSettlementDetuction(models.Model):
    _inherit = 'employee.vacation.settlement.detuction'
    _description = 'Employee Vacation Settlement Deduction'

    service_id = fields.Many2one('hr.end.service.benefit', string='Deductions End Service', ondelete='cascade')


class EmployeeVacationSettlementAllowance(models.Model):
    _inherit = 'employee.vacation.settlement.allowance'
    _description = 'Employee Vacation Settlement Deduction'

    service_id = fields.Many2one('hr.end.service.benefit', string='Allowances End Service', ondelete='cascade')


class HolidaysReward(models.Model):
    _name = 'hr.end.benefit.holiday.line'
    _description = 'Holiday Reward'

    def get_allocation_remaining_display(self):
        current_date = fields.Date.today()
        time_off_taken_new = self.env['hr.leave']
        allocations = self.env['hr.leave.allocation'].search([
            ('employee_id', 'in', self.employee_id.ids),
            ('state', '=', 'validate'),
            ('holiday_status_id', '=', self.holiday_id.id)
        ])

        for employee in self.employee_id:
            employee_remaining_leaves = 0
            employee_max_leaves = 0
            employee_allocations = allocations.filtered(lambda a: a.employee_id == employee)

            for allocation in employee_allocations:
                leave_type = allocation.holiday_status_id
                days_taken = 0

                time_off_taken = self.env['hr.leave'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'validate'),
                    ('holiday_status_id', '=', leave_type.id),
                    ('request_date_from', '>=', allocation.date_from or False),
                    ('request_date_to', '<=', allocation.date_to or current_date)
                ])
                if not time_off_taken_new or time_off_taken_new != time_off_taken:
                    days_taken = sum(leave.number_of_days for leave in time_off_taken)
                    time_off_taken_new = time_off_taken
                remaining = allocation.number_of_days_display - days_taken

                employee_remaining_leaves += remaining if leave_type.request_unit in ['day', 'half_day'] \
                    else remaining / (employee.resource_calendar_id.hours_per_day or HOURS_PER_DAY)

                employee_max_leaves += allocation.number_of_days_display
            print('employee_remaining_leaves >>> ', employee_remaining_leaves)

            return employee_remaining_leaves

    # ToDo:Refactor
    @api.depends('holiday_id')
    def _compute_leaves(self):
        for record in self:
            record.remaining_leaves = 0
            get_allocation_remaining_display = record.get_allocation_remaining_display()
            # contract = self.env['hr.contract'].search(
            #     [('employee_id', '=', self.employee_id.id)], limit=1, order='id desc')
            # if record.reward_id and record.reward_id.type == 'ending_service' or record.reward_id.type == 'replacement':
            #     data_days = {}
            #     employee_id = record.reward_id.employee_id
            #     if employee_id:
            #         employee_record = self.env['hr.employee'].browse([employee_id.id])
            #         allocation_data = record.holiday_id.get_allocation_data(employee_record)
            #         data_days = allocation_data.get(employee_id.id, {})

            #     for holiday_status in record.holiday_id:
            #         if data_days:
            #             result = data_days.get(holiday_status.id, {})
            #             remaining_leaves = result.get('remaining_leaves', 0)
            #             if holiday_status.request_unit == 'hour':
            #                 remaining_leaves = remaining_leaves / (
            #                         employee_id.company_id.number_of_hours_per_day or 8)
            #             elif holiday_status.request_unit == 'half_day':
            #                 remaining_leaves = remaining_leaves / 2
            #             record.remaining_leaves = remaining_leaves
            record.remaining_leaves = get_allocation_remaining_display

    holiday_id = fields.Many2one(comodel_name="hr.leave.type", string="Holiday", required=False)
    reward_id = fields.Many2one(comodel_name="hr.end.service.benefit")
    employee_id = fields.Many2one(comodel_name="hr.employee", related='reward_id.employee_id')
    remaining_leaves = fields.Float(string="Remaining Leaves", compute='_compute_leaves', store=True)
    pay = fields.Boolean(string="Pay As Reward")


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super().action_post()
        for rec in self:
            hr_end_service = self.env['hr.end.service.benefit'].search([('account_move_id', '=', rec.id)])
            if hr_end_service:
                hr_end_service.write({'state': 'post'})
        return res
