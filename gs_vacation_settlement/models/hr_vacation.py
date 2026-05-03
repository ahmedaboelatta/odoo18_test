# -*- coding: utf-8 -*-

##############################################################################
#    Maintainer: Eng.Mohamed Abdalla <mohamedabdalla142001@gmail.com>
#    It is forbidden to publish, distribute, sublicense, or sell copies
#    of the Software or modified copies of the Software.
##############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError,UserError
from datetime import timedelta


class EmployeeVacationSettlement(models.Model):
    _name = "employee.vacation.settlement"
    _description = "Employee Vacation Settlement"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.model
    def _default_journal_id(self):
        """ The journal is determining the company of the accounting entries generated from expense. We need to force journal company and expense sheet company to be the same. """
        default_company_id = self.default_get(['company_id'])['company_id']
        journal = self.env['account.journal'].search([('is_vacation', '=', True)], limit=1)
        return journal.id

    def _default_type_amount_due(self):
        amount_default=self.env['type.allowances'].search([('type', '=', 'amountdue')], limit=1)
        return amount_default
    def _default_type_ticket(self):
        ticket_default=self.env['type.allowances'].search([('type', '=', 'ticket')], limit=1)
        return ticket_default

    # def _default_account_move_id(self):
    #     default_account_move_id= self.env['account.move'].search([ ('ref', '=', self.name)],limit=1)
    #     return default_account_move_id




    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, default=lambda self: self.env.company)
    employee_id = fields.Many2one('hr.employee', string="Employee", required=True)
    department_id = fields.Many2one(related='employee_id.department_id', string='Department', store=True)
    job_id = fields.Many2one(related='employee_id.job_id', string='Position', store=True)
    partner_emp= fields.Many2one(string='Partner Related', related='employee_id.address_home_id', store=True) #related='employee_id.address_home_id',#####?????
    job_title = fields.Char(related='employee_id.job_title', string='Position Number', store=True)
    register_num = fields.Char(related='employee_id.registration_number2', string='Employee Code', store=True)
    current_contract_id = fields.Many2one('hr.contract', string='Current Contract', default=lambda self: self.env.context.get('active_id'), domain="[('employee_id', '=', employee_id)]")
    start_date_work = fields.Date(related='current_contract_id.date_start', string="Start Date", store=True)
    total_salary = fields.Monetary(related='current_contract_id.total_package_val', string='Total Salary Value', currency_field='currency_id', readonly=True, store=True)
    currency_id = fields.Many2one('res.currency', string='Currency')
    leave_id = fields.Many2one('hr.leave', string="Leave", required=True, domain="[('state', '=', 'validate'), ('employee_id', '=', employee_id),('holiday_status_id.work_entry_type_id.code', '=', 'LEAVE120')]")
    leave_start_date = fields.Date(related='leave_id.request_date_from', string='Leave Start Date', store=True)
    leave_end_date = fields.Date(related='leave_id.request_date_to', string='Number of Vacation Days', store=True)
    num_of_vacation = fields.Integer(string='Number of Vacation Days', compute='_compute_num_of_vacation', readonly=True)
    last_work_date = fields.Date(string='Date of Last Work')
    payslip_id = fields.Many2one(comodel_name="hr.payslip", string="Payslip", tracking=True)
    payslip_ids = fields.Many2many(comodel_name="hr.payslip", string="Payslip", tracking=True)
    days_number = fields.Float(string="Last Month Worked Days Number", default=30, tracking=True)
    total_payslip_deserved_amount = fields.Float(string="Total Payslip Deserved Amount", tracking=True,
                                                 compute='_compute_total_payslip_deserved_amount', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('approve', 'Approved'),
        ('post', 'Posted'),
        ('done', 'Done'),
        ('pay', 'Payed'),
        ('refuse', 'Refused'),
        ('cancel', 'Canceled'),
    ], string="State", default='draft', track_visibility='onchange', copy=False)
    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    number_of_days_of_allowances = fields.Float(related='leave_id.number_of_days_display', string='The number of days due from the forecast to date', readonly=True ,compute="")
    financially_accrued_leave = fields.Integer(string='Financially Accrued Leave')
    remaining_vacation_balance_after_settlement = fields.Integer(string='The remaining vacation balance after settlement is financial', compute='_balance_after_financial')
    remaining_vacation_balance_working_days = fields.Integer(string='The remaining vacation balance after working days', compute='_balance_after_working_days')
    contract_type = fields.Many2one(related='current_contract_id.contract_type_id', string='Contract Type', store=True)
    contract_period = fields.Date(related='current_contract_id.trial_date_end', string='Contract Period', store=True)
    vacation_allowance_pay = fields.Monetary(related='current_contract_id.vacation_total_amount', string='Vacation Allowance Pay')
    todays_pay = fields.Monetary(string="Today's Pay", compute='_compute_todays_pay')
    amount_due = fields.Float(string='Amount Due', compute='_compute_amount_due')
    end_date_work = fields.Date(related='current_contract_id.date_end', string="End Date", store=True)
    ticket1 = fields.Boolean(related='current_contract_id.ticket1')
    tickets_no_company = fields.Integer(string="No. Of Tickets", related='current_contract_id.tickets_no_company')
    tickets_val_company = fields.Integer(string="Tickets Value", related='current_contract_id.tickets_val_company')
    allowance_ids = fields.One2many('employee.vacation.settlement.allowance', 'settlement_id', string="Allowances" , )
    total_allowances = fields.Monetary(string="Total Allowances", compute='_compute_total_allowances', store=True)
    detuction_ids = fields.One2many('employee.vacation.settlement.detuction', 'settlement_id', string="Detuctions")
    total_detuction = fields.Monetary(string="Total Detuction", compute='_compute_total_detuction', store=True)
    recipient_users = fields.Text()
    total_employee_id = fields.One2many('total.employee','settlement_ids' ,string="Total Employee")
    type_allowances = fields.Many2one('type.allowances', string="Type of Allowance", ondelete='cascade', domain=[('type', '=', 'allwances')], store=True)
    type_detuction = fields.Many2one('type.allowances', string="Type of Detuction", ondelete='cascade' ,
    domain=[('type','=','deduction')]
    )
    type_amount_due = fields.Many2one('type.allowances', string="Type of Amount Due", required=True, ondelete='cascade', domain=[('type', '=', 'amountdue')], store=True ,
    default=_default_type_amount_due,
    )
    type_ticket = fields.Many2one('type.allowances', string="Type of Amount Due", required=False, ondelete='cascade', domain=[('type', '=', 'ticket')], store=True ,
    default=_default_type_ticket,
    )

    account_move_id = fields.Many2one('account.move', string='Journal Entry'  , compute="_compute_account_move_id")
    name_account_move = fields.Char(related='account_move_id.name',string="Journal Entries Name")
    payment_mode = fields.Selection([
        ("own_account", "Employee (to reimburse)"),
        ("company_account", "Company")
    ], default='own_account', tracking=True, states={'done': [('readonly', True)], 'approved': [('readonly', True)], 'reported': [('readonly', True)]}, string="Paid By")
    journal_id = fields.Many2one('account.journal', string='vacation Journal', domain="[('is_vacation', '=', True)]",
        default=_default_journal_id, help="The journal used when the expense is done.")
    account_id = fields.Many2one(
            'account.account',
            string='Account',
            help="An expense account is expected"
        )
    total_total = fields.Float(string="Total", compute='_compute_total')
    total_total_word = fields.Char(string="Total in Words", compute='_compute_total_total_word')
    other_deduction = fields.Float(
        string="Other Deduction",
        compute="_compute_other_deduction",
        store=True
    )

    @api.depends('detuction_ids.detuction', 'detuction_ids.type_detuction')
    def _compute_other_deduction(self):
        for rec in self:
            rec.other_deduction = sum(
                rec.detuction_ids.filtered(
                    lambda l: l.type_detuction and l.type_detuction.is_type_collected
                ).mapped('detuction')
            )
    other_allowance = fields.Float(string="Other Allowance")
    total_net_payslip = fields.Float(string="Total Net Payslip", compute='_compute_total_net_payslip', store=True)
    paid_status = fields.Selection([
        ('paid', 'Paid'),
        ('partial', 'Partial Paid'),
        ('not_paid', 'Not Paid')
    ], default='not_paid')
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

    def _compute_account_move_id(self):
        for rec in self:
            if rec.state == 'post' or rec.state == 'pay'  :
                rec.account_move_id = self.env['account.move'].search([ ('ref', '=', self.name)],limit=1)
            else :
                rec.account_move_id = False

    @api.depends('employee_id', 'payslip_ids', 'payslip_ids.line_ids', 'days_number', )
    def _compute_total_payslip_deserved_amount(self):
        for record in self:
            payslip_total = 0
            for payslip in record.payslip_ids:
                net_lines = self.env['hr.payslip.line'].search([
                    ('slip_id', '=', payslip.id), ('code', '=', 'NET')
                ])
                for line in net_lines:
                    payslip_total += line.total
            record.total_payslip_deserved_amount = payslip_total

    # @api.depends('employee_id', 'payslip_id', 'payslip_id.line_ids', 'days_number', )
    # def _compute_total_payslip_deserved_amount(self):
    #     for record in self:
    #         payslip_total = 0
    #         net_lines = self.env['hr.payslip.line'].search([
    #                 ('slip_id', '=', record.payslip_id.id), ('code', '=', 'NET')
    #             ])
    #         for line in net_lines:
    #             payslip_total += line.total
    #         record.total_payslip_deserved_amount = payslip_total

    @api.depends('amount_due', 'total_allowances', 'tickets_val_company', 'total_detuction', 'total_payslip_deserved_amount')
    def _compute_total(self):
        for record in self:
            record.total_total = (
                record.amount_due +
                record.total_payslip_deserved_amount +
                record.total_allowances +
                record.tickets_val_company +
                record.other_allowance -
                record.total_detuction
            )


    @api.onchange('leave_id')
    def _compute_number_of_days_of_allowances(self):
        for record in self:
             if record.leave_id:
                record.number_of_days_of_allowances = record.leave_id.number_of_days_display
             else:
                record.number_of_days_of_allowances = 0.0





    # @api.depends('company_id')
    # def _compute_account_id(self):
    #     for record in self:
    #         if not record.account_id:
    #             record.account_id = self.env['account.account'].search([
    #                 ('company_id', '=', record.company_id.id)
    #             ], limit=1)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('employee.vacation.settlement') or _('New')
        return super(EmployeeVacationSettlement, self).create(vals)


    @api.onchange('last_work_date')
    def _check_last_work_date(self):
        for record in self:
           if record.last_work_date and record.leave_start_date:
                if record.last_work_date >= record.leave_start_date:
                    if record.last_work_date > record.leave_start_date:
                        raise ValidationError("The Date of Last Work must be before the Leave Start Date.")
                    else:
                        raise ValidationError("The Date of Last Work can't be the Leave Start Date.")

    @api.onchange('leave_end_date')
    def _compute_num_of_vacation(self):
        for record in self:
            if record.leave_start_date and record.leave_end_date:
                delta = (record.leave_end_date - record.leave_start_date)
                record.num_of_vacation = delta.days +1

    @api.depends('financially_accrued_leave', 'number_of_days_of_allowances')
    @api.onchange('financially_accrued_leave')
    def _balance_after_financial(self):
        for record in self:
            x = float(record.number_of_days_of_allowances)
            record.remaining_vacation_balance_after_settlement = int(x) - record.financially_accrued_leave

    @api.onchange('financially_accrued_leave')
    def _balance_after_working_days(self):
        for record in self:
            x = float(record.number_of_days_of_allowances)
            record.remaining_vacation_balance_working_days = int(x) - record.num_of_vacation



    @api.onchange('employee_id')
    def _compute_all_allowances(self):
        type=self.env['type.allowances'].search([('type', '=', 'allwances')])
        line = [(5, 0, 0)]
        for record in type:
            val = {
            	 'type_allowances': record.id,
            }
            line.append((0, 0, val))
            self.allowance_ids = line

    @api.onchange('employee_id')
    def _compute_all_detuction(self):
        type=self.env['type.allowances'].search([('type', '=', 'deduction')])
        line = [(5, 0, 0)]
        for record in type:
            val = {
            	 'type_detuction': record.id,
            }
            line.append((0, 0, val))
            self.detuction_ids = line





    @api.depends('allowance_ids.other_allowances')
    @api.onchange('allowance_ids')
    def _compute_total_allowances(self):
        for record in self:
            total = 0
            for allowance in record.allowance_ids:
                    total += allowance.other_allowances
            record.total_allowances = total


    @api.depends('detuction_ids.detuction')
    @api.onchange('detuction_ids')
    def _compute_total_detuction(self):
        for record in self:
            total = 0
            for detuction in record.detuction_ids:
                  total += detuction.detuction
            record.total_detuction = total


    @api.onchange('vacation_allowance_pay')
    def _compute_todays_pay(self):
        for record in self:
            record.todays_pay = record.vacation_allowance_pay / 30

    @api.onchange('financially_accrued_leave')
    def _compute_amount_due(self):
        for line in self:
            line.amount_due = line.todays_pay * line.financially_accrued_leave

    def action_reset_to_draft(self):
        return self.write({'state': 'draft'})

    def action_refuse(self):
        return self.write({'state': 'refuse'})

    def action_submit(self):
        self.write({'state': 'submit'})

    def action_cancel(self):
        self.write({'state': 'cancel'})
        AccountMove = self.env['account.move'].search([ ('ref', '=', self.name)])
        if AccountMove:
            AccountMove.button_draft()
            AccountMove.button_cancel()
            AccountMove.unlink()
        self.paid_status = 'not_paid'

    def action_approve(self):
        self.write({'state': 'approve'})

    @api.depends('total_total', 'currency_id')
    def _compute_total_total_word(self):
        for record in self:
            if record.total_total and record.currency_id:
                record.total_total_word = record.total_amount_in_words('ar_AA', record.total_total)
            else:
                record.total_total_word = ""

    def total_amount_in_words(self, lang, total_total):
        self.ensure_one()  # Ensure the record is a singleton
        return self.currency_id.with_context(lang=lang).amount_to_text(total_total)






    def action_sheet_move_create(self):
        if any(sheet.state != 'approve' for sheet in self):
            raise UserError(_("You can only generate accounting entry for approved settlement(s)."))

        if not self.employee_id.sudo().address_home_id:
            raise UserError(_("The private address of the employee is required to post the settlement. Please add it on the employee form."))

        # if not self.account_id:
        #     raise UserError(_("Specify a default account to balance the journal entries."))

        journal = self.env['account.journal'].search([('type', '=', 'general')], limit=1)
        if not journal:
            raise UserError(_("General journal not found."))

        move_vals = {
            'journal_id': self.journal_id.id,
            'date': fields.Date.context_today(self),
            'ref': self.name,
            'line_ids': [],
        }

        total_debit = 0
        total_credit = 0

        for line in self.allowance_ids:
            if not line.type_allowances.account:
                raise UserError(_("Account for type allowances not found."))
            move_vals['line_ids'].append((0, 0, {
                'account_id': line.type_allowances.account.id,
                'partner_id': self.employee_id.address_home_id.id,
                'name': line.other_allowances_note,
                'debit': line.other_allowances,
                'credit': 0,
                'analytic_distribution': {
                    self.analytic_account_id.id: 100} if self.analytic_account_id else False,

            }))
            total_debit += line.other_allowances

        for line in self.detuction_ids:
            if not line.type_detuction.account:
                raise UserError(_("Account for type deduction not found."))
            move_vals['line_ids'].append((0, 0, {
                'account_id': line.type_detuction.account.id,
                'partner_id': self.employee_id.address_home_id.id,
                'name': line.detuction_note,
                'debit': 0,
                'credit': line.detuction,
                'analytic_distribution': {
                    self.analytic_account_id.id: 100} if self.analytic_account_id else False,

            }))
            total_credit += line.detuction

        # Adding amount_due to the journal entry
        amount_due = self.amount_due
        default_account = self.env['account.account'].search([], limit=1)
        if not default_account:
            raise UserError(_("Default account not found."))

        move_vals['line_ids'].append((0, 0, {
            'account_id': self.type_amount_due.account.id,
            'partner_id': self.employee_id.address_home_id.id,
            'name': _("Amount Due"),
            'debit': amount_due ,
            'credit': 0,
            'analytic_distribution': {
                self.analytic_account_id.id: 100} if self.analytic_account_id else False,

        }))
        total_debit += amount_due
        # Add ticket to the journal entry
        if self.ticket1:
            ticket = self.tickets_val_company
            move_vals['line_ids'].append((0, 0, {
                'account_id': self.type_ticket.account.id,
                'partner_id': self.employee_id.address_home_id.id,
                'name': _("Ticket Value"),
                'debit': ticket,
                'credit': 0,
                'analytic_distribution': {
                    self.analytic_account_id.id: 100} if self.analytic_account_id else False,

            }))
            total_debit += ticket
        if self.payslip_ids:
            payroll_account = self.env['type.allowances'].search([('is_payroll', '=', True)], limit=1)
            if not payroll_account or not payroll_account.account:
                raise ValidationError(_('Please Add Account To Payroll in Type Allowance'))
            move_vals['line_ids'].append((0, 0, {
                'account_id': payroll_account.account.id,
                'partner_id': self.employee_id.address_home_id.id,
                'name': _("Payroll"),
                'debit': self.total_payslip_deserved_amount,
                'credit': 0,
                'analytic_distribution': {
                    self.analytic_account_id.id: 100} if self.analytic_account_id else False,

            }))
            total_debit += self.total_payslip_deserved_amount
        # Calculate the balancing amount
        balancing_amount = total_debit - total_credit
        if not self.employee_id.bank_account_id:
            raise UserError(_("Employee bank account not found."))

        # Add balancing line
        move_vals['line_ids'].append((0, 0, {
            'account_id':self.journal_id.gs_def_debit_acc.id,
            'partner_id': self.employee_id.address_home_id.id,
            'name': 'Balancing Entry',
            'debit': 0 if balancing_amount > 0 else -balancing_amount,
            'credit': balancing_amount if balancing_amount > 0 else 0,
            'analytic_distribution': {
                self.analytic_account_id.id: 100} if self.analytic_account_id else False,

        }))

        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.write({'state': 'post'})



    def action_open_account_move(self):
        self.ensure_one()
        AccountMove = self.env['account.move'].search([ ('ref', '=', self.name)])
        return {
            # 'name': AccountMove.name,
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            # 'views': [[False, "form"]],
            'res_model': 'account.move',
            # 'res_id': AccountMove.id,
            'domain':[('id', 'in', AccountMove.ids)],
        }


    def action_register_payment(self):
        ''' Open the account.payment.register wizard to pay the selected journal entries.
        There can be more than one bank_account_id in the expense sheet when registering payment for multiple expenses.
        The default_partner_bank_id is set only if there is one available, if more than one the field is left empty.
        :return: An action opening the account.payment.register wizard.
        '''
        AccountMove = self.env['account.move'].search([ ('ref', '=', self.name)],limit=1)

        # self.write({'state': 'pay'})
        return {
            'name': _('Register Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'context': {
                'active_model': 'account.move',
                'active_ids': self.account_move_id.ids,
                'default_partner_bank_id': self.employee_id.sudo().bank_account_id.id,
                'default_hr_vacation_id': self.id,

            },
            'target': 'new',
            'type': 'ir.actions.act_window',


        }















# allowances model
class EmployeeVacationSettlementAllowance(models.Model):
    _name = 'employee.vacation.settlement.allowance'
    _description = 'Employee Vacation Settlement Allowance'

    account_id =  fields.One2many('account.move.line', 'allowance_ids', string='Matched Journal Items' , store=True)
    settlement_id = fields.Many2one('employee.vacation.settlement', string='Vacation Settlement')
    other_allowances = fields.Monetary(string="Other Allowances", compute='_compute_balance', store=True)
    other_allowances_note = fields.Text(string='Description')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    type_allowances = fields.Many2one('type.allowances', string="Type of Allowance", required=True, ondelete='cascade', domain=[('type', '=', 'allwances')], store=True)

    @api.depends('account_id.balance', 'settlement_id.employee_id')
    @api.onchange('type_allowances')
    def _compute_balance(self ):
        pass
        # for record in self:
        #     record.other_allowances = 0
        #     if record.settlement_id:
        #         employee_partner_id = record.settlement_id.employee_id.address_home_id.id
        #         cash_advance_lines = self.env['account.move.line'].search([
        #             ('partner_id', '=', employee_partner_id),
        #             ('account_id', '=', record.type_allowances.account.id)
        #         ])
        #         record.other_allowances = sum(cash_advance_lines.mapped('balance'))

class EmployeeVacationSettlementDetuction(models.Model):
    _name = 'employee.vacation.settlement.detuction'
    _description = 'Employee Vacation Settlement detuction '

    account_id =  fields.One2many('account.move.line', 'allowance_ids', string='Matched Journal Items' , store=True)
    settlement_id = fields.Many2one('employee.vacation.settlement', string='Detuction Settlement')
    detuction = fields.Monetary(string="Detuction Money",compute='_compute_balance', store=True)
    detuction_note = fields.Text(string='Description')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    type_detuction = fields.Many2one('type.allowances', string="Type of Detuction", required=True, ondelete='cascade' ,
    domain=[('type','=','deduction')]
    )
    @api.depends('account_id.balance', 'settlement_id.employee_id', 'type_detuction')
    @api.onchange('type_detuction')
    def _compute_balance(self ):
        pass
        # for record in self:
        #     record.detuction = 0
        #     if record.settlement_id:
        #         employee_partner_id = record.settlement_id.employee_id.address_home_id.id
        #         cash_advance_lines = self.env['account.move.line'].search([
        #             ('partner_id', '=', employee_partner_id),
        #             ('account_id', '=', record.type_detuction.account.id)
        #         ])
        #         record.detuction = sum(cash_advance_lines.mapped('balance'))



class TypeAllowances(models.Model):
    _name = 'type.allowances'
    _description = 'Type of Allowance'

    name = fields.Char(string='Allowance Type')
    type = fields.Selection(string='Type', selection=[('deduction', 'Deduction'),('allwances', 'Allowances'), ('amountdue', 'Amount Due'),('ticket', 'Ticket'),
                                                      ],)
    account = fields.Many2one('account.account', string='Chart of Account', required=True, domain=[('deprecated', '=', False)])
    is_type_collected = fields.Boolean(string='Other')
    description = fields.Text(string='Description')
    is_payroll = fields.Boolean('Payroll')
    eos_vacation = fields.Boolean('EOS Vacation')

class AccountAccount(models.Model):
    _inherit = 'account.account'

    is_allowances = fields.Boolean()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    settlement_id = fields.Many2one('employee.vacation.settlement', string='Vacation Settlement', required=True, ondelete='cascade')
    allowance_ids = fields.Many2one('employee.vacation.settlement.allowance',string="Allowances")




class Total(models.Model):
    _name = 'total.employee'
    _description = 'Total Employee'  # Added description

    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    total_allowances = fields.Monetary(string="Total Allowances", related='settlement_ids.total_allowances')  # Completed field definition
    tickets_val_company = fields.Integer(string="Tickets Value Company" , related='settlement_ids.tickets_val_company')  # Completed field definition
    total_detuction = fields.Monetary(string="Total Detuction" , related='settlement_ids.total_detuction')  # Completed field definition
    settlement_ids = fields.Many2one('employee.vacation.settlement', string="Vacation Settlements", required=True, ondelete='cascade')  # Added One2many field
    amount_due = fields.Float(string="Total amount Due", related='settlement_ids.amount_due')

