# -*- coding: utf-8 -*-
# Copyright 2019 Coop IT Easy SCRL fs
#   Robin Keunen <robin@coopiteasy.be>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models ,_
from dateutil.relativedelta import relativedelta
from datetime import date, datetime, time


class ContractsAllowance(models.Model):
    _name = 'hr.contract.allowance'
    _description = 'Contracts Allowances'

    contract_id = fields.Many2one('hr.contract')
    employee_id = fields.Many2one('hr.employee')
    allowance_id = fields.Many2one('hr.allowance', 'Allowance')
    currency_id = fields.Many2one(string="Currency", related='contract_id.company_id.currency_id', readonly=True)
    name = fields.Char('Allowance')
    amount = fields.Monetary(string="Amount")
    is_paid = fields.Boolean(string="Paid",default=True)

    # not used
    calc_type = fields.Selection([('percent','Percentage'),('amount','Amount')],string="Calculation")
    percentage = fields.Float(string="Percentage")


    # @api.depends('house_allowance_slc','house_allowance_per','wage')
    # def _house_allowance_func(self):
    #     for line in self:
    #         line.is_house_per = False
    #         if line.house_allowance_slc == 'percent':
    #             line.is_house_per = True
    #             percentage = 0
    #             if line.house_allowance_per:
    #                 percentage = line.house_allowance_per / 100
    #             line.house_allowance_val = line.wage * percentage
    #         else:
    #             line.house_allowance_per = 0

class ContractsInherit(models.Model):
    _inherit = 'hr.contract'
    _description = 'Contracts Inheritance'

    wage = fields.Monetary('Basic Salary', required=True, tracking=True, help="Employee's monthly gross wage.")

    contract_allowances = fields.One2many('hr.contract.allowance','contract_id')
    identification_id = fields.Char(string='Identification No', groups="hr.group_hr_user", tracking=True, related='employee_id.identification_id')

    is_paid_housing = fields.Boolean('Paid', default=True)
    is_paid_trans = fields.Boolean('Paid', default=True)
    is_paid_other = fields.Boolean('Paid', default=True)
    is_paid_car = fields.Boolean('Paid', default=True)
    is_paid_petrol = fields.Boolean('Paid', default=True)
    is_paid_food = fields.Boolean('Paid', default=True)
    is_paid_calls = fields.Boolean('Paid', default=True)
    is_paid_overtime = fields.Boolean('Paid', default=True)
    is_paid_work_nat = fields.Boolean('Paid', default=True)
    is_paid_occ_haz = fields.Boolean('Paid', default=True)
    is_paid_school = fields.Boolean('Paid', default=True)

    is_paid_other_ded = fields.Boolean('Paid', default=True)
    is_paid_eos_house = fields.Boolean('Paid', default=True)
    is_paid_eos_trans = fields.Boolean('Paid', default=True)
    is_paid_vac_house = fields.Boolean('Paid', default=True)
    is_paid_vac_trans = fields.Boolean('Paid', default=True)
    run_fun_many = fields.Boolean(compute='_compute_get_default_data')
    update_vacation = fields.Boolean()
    update_eos = fields.Boolean()

    collect_allowances_eos = fields.Many2many('allowances.collect','column01','column02','column03')
    collect_allowances_vacation = fields.Many2many('allowances.collect','x_column01','x_column02','x_column03',)

    eos_total_amount = fields.Monetary('EOS Total Amount', readonly=1)
    eos_total_amount_month = fields.Monetary('EOS Monthly', readonly=1)
    vacation_total_amount = fields.Monetary('Vacation Total Amount',readonly=1)
    experience = fields.Char(string='Experience', compute='_compute_experience')
    attachment_contract = fields.Binary(string="Attachment", )
    has_contract = fields.Boolean('Contract Attachment?')
    iqama_renew_premium = fields.Monetary(string="Iqama Renew Premium")
    medical_insurance = fields.Monetary(string="Medical Insurance")

    ticket1 = fields.Boolean(string='Ticket')
    ticket_type = fields.Selection(string='Ticket', selection=[('economy', 'Economy'), ('business', 'Business'), ], )
    ticket_value = fields.Integer(string='Ticket Value', )
    paid_by_company = fields.Boolean(string='Paid By Company')
    run_function = fields.Boolean(compute="_compute_run_function")
    contract_duration_id = fields.Many2one('gs.contract.duration', string='Contract Duration')

    def _compute_run_function(self):
        for rec in self:
            rec.run_function = False
            rec._onchange_eos_total_amount()

    # @api.onchange('ticket_type', 'country_id')
    # def _onchange_ticket_type(self):
    #     for rec in self:
    #         if rec.employee_id.country_id:
    #             tickets = self.env['gs.tickets'].search([('country_id', '=', rec.employee_id.country_id.id)], limit=1)
    #             if rec.ticket_type == 'economy':
    #                 self.ticket_value = tickets.economy_fare
    #             if rec.ticket_type == 'business':
    #                 self.ticket_value = tickets.business_class_fare

    def _compute_experience(self):
        if self.first_contract_date:
            rd = relativedelta(date.today(), self.first_contract_date)
            self.experience = str(rd.years) + ' Years & ' + str(rd.months) + ' Months & ' + str(
                rd.days) + ' Days'

    @api.onchange('eos_total_amount')
    def _onchange_eos_total_amount(self):
        for rec in self:
            rec.eos_total_amount_month = rec.eos_total_amount / 12

    # @api.onchange('employee_id')
    # def _onchange_gs_employee_id(self):
    #     for rec in self:
    #         rec.collect_allowances_eos = [(4, self.env.ref('gs_hr_contract_allowance.gs_basic_salary').id)]
    #         rec.collect_allowances_eos = [(4, self.env.ref('gs_hr_contract_allowance.gs_transportation_amount').id)]
    #         rec.collect_allowances_eos = [(4, self.env.ref('gs_hr_contract_allowance.gs_house_amount').id)]
    #
    #         rec.collect_allowances_vacation = [(4, self.env.ref('gs_hr_contract_allowance.gs_basic_salary').id)]
    #         rec.collect_allowances_vacation = [(4, self.env.ref('gs_hr_contract_allowance.gs_transportation_amount').id)]
    #         rec.collect_allowances_vacation = [(4, self.env.ref('gs_hr_contract_allowance.gs_house_amount').id)]
    #
    def _compute_get_default_data(self):
        for rec in self:
            rec.run_fun_many = True
            if not rec.collect_allowances_eos and rec.update_eos:
                rec.collect_allowances_eos = [(4, self.env.ref('gs_hr_contract_allowance.gs_basic_salary').id)]
                rec.collect_allowances_eos = [(4, self.env.ref('gs_hr_contract_allowance.gs_transportation_amount').id)]
                rec.collect_allowances_eos = [(4, self.env.ref('gs_hr_contract_allowance.gs_house_amount').id)]
            if not rec.collect_allowances_vacation and rec.update_vacation:
                rec.collect_allowances_vacation = [(4, self.env.ref('gs_hr_contract_allowance.gs_basic_salary').id)]
                rec.collect_allowances_vacation = [(4, self.env.ref('gs_hr_contract_allowance.gs_transportation_amount').id)]
                rec.collect_allowances_vacation = [(4, self.env.ref('gs_hr_contract_allowance.gs_house_amount').id)]
            rec._onchange_collect_eos_allowances()
            rec._onchange_eos_total_amount()
            rec._onchange_collect_vacation_allowances()

    @api.onchange('collect_allowances_eos', 'house_allowance_val', 'trans_allowance_val', 'wage', 'date_start', 'date_end')
    def _onchange_collect_eos_allowances(self):
        eos_amount = 0
        self.eos_total_amount = 0
        for line in self.collect_allowances_eos:
            if self._fields['house_allowance_val'].string == line.name:
                eos_amount += self.house_allowance_val
            if self._fields['trans_allowance_val'].string == line.name:
                eos_amount += self.trans_allowance_val
            if self._fields['wage'].string == line.name:
                eos_amount += self.wage
            for allowances in self.contract_allowances:
                if allowances.allowance_id.name == line.name:
                    eos_amount += allowances.amount

            # if self._fields['other_allowance_val'].string == line.name:
            #     eos_amount += self.other_allowance_val
            # if self._fields['car_allowance'].string == line.name:
            #     eos_amount += self.car_allowance
            # if self._fields['petrol_allowance'].string == line.name:
            #     eos_amount += self.petrol_allowance
            # if self._fields['food_allowance'].string == line.name:
            #     eos_amount += self.food_allowance
            # if self._fields['calls_allowance'].string == line.name:
            #     eos_amount += self.calls_allowance
            # if self._fields['overtime_allowance'].string == line.name:
            #     eos_amount += self.overtime_allowance
            # if self._fields['work_nat_allowance'].string == line.name:
            #     eos_amount += self.work_nat_allowance
            # if self._fields['occ_haz_allowance'].string == line.name:
            #     eos_amount += self.occ_haz_allowance
            # if self._fields['school_allowance'].string == line.name:
            #     eos_amount += self.school_allowance
        if self.date_end:
            rd = relativedelta(self.date_end, self.date_start)
            if rd.years < 5:
                self.eos_total_amount = eos_amount / 2
            else:
                self.eos_total_amount = eos_amount
        else:
            date_end = fields.Date.today()
            rd = relativedelta(date_end, self.date_start)
            if rd.years < 5:
                self.eos_total_amount = eos_amount / 2
            else:
                self.eos_total_amount = eos_amount

    @api.onchange('collect_allowances_vacation', 'house_allowance_val', 'trans_allowance_val', 'wage')
    def _onchange_collect_vacation_allowances(self):
        vac_amount = 0
        self.vacation_total_amount = 0
        for line in self.collect_allowances_vacation:
            if self._fields['house_allowance_val'].string == line.name:
                vac_amount += self.house_allowance_val
            if self._fields['trans_allowance_val'].string == line.name:
                vac_amount += self.trans_allowance_val
            if self._fields['wage'].string == line.name:
                vac_amount += self.wage
            for allowances in self.contract_allowances:
                if allowances.allowance_id.name == line.name:
                    vac_amount += allowances.amount

            # if self._fields['other_allowance_val'].string == line.name:
            #     vac_amount += self.other_allowance_val
            # if self._fields['car_allowance'].string == line.name:
            #     vac_amount += self.car_allowance
            # if self._fields['petrol_allowance'].string == line.name:
            #     vac_amount += self.petrol_allowance
            # if self._fields['food_allowance'].string == line.name:
            #     vac_amount += self.food_allowance
            # if self._fields['calls_allowance'].string == line.name:
            #     vac_amount += self.calls_allowance
            # if self._fields['overtime_allowance'].string == line.name:
            #     vac_amount += self.overtime_allowance
            # if self._fields['work_nat_allowance'].string == line.name:
            #     vac_amount += self.work_nat_allowance
            # if self._fields['occ_haz_allowance'].string == line.name:
            #     vac_amount += self.occ_haz_allowance
            # if self._fields['school_allowance'].string == line.name:
            #     vac_amount += self.school_allowance

        self.vacation_total_amount = vac_amount

    emp_type = fields.Selection([('saudi', 'Saudi'),('not_saudi','Non Saudi')], string='Type', related="employee_id.type")
    gosi_number = fields.Char(string='GOSI Number', help="Gosi Number",related="employee_id.gosi_number")
    issue_date = fields.Date(string='Issued Date', help="Issued Date",related="employee_id.issue_date")

    company_share_per = fields.Float('Company Share %',compute="_compute_share_amount",store=1)
    company_share_amount = fields.Float('Company Share Amount',compute="_compute_share_amount",store=1)
    employee_share_per = fields.Float('Employee Share %',compute="_compute_share_amount",store=1)
    employee_share_amount = fields.Float('Employee Share Amount',compute="_compute_share_amount",store=1)
    gosi_salary_amount = fields.Float('Gosi Salary', compute='_compute_gosi_salary', store=1)
    maximum_gosi_salary = fields.Float('Maximum Gosi Salary',compute="_compute_share_amount",store=1)
    date_hired = fields.Date('Hire Date', readonly=True, compute='_compute_get_hire_date')

    def _compute_get_hire_date(self):
        for rec in self:
            history = self.env['hr.contract.history'].search([('employee_id', '=', rec.employee_id.id)], limit=1)
            rec.date_hired = history.date_hired

    @api.model
    def _default_gosi_config(self):
        gosi_config = self.env['gosi.config'].search([], limit=1)
        if gosi_config:
            return gosi_config.id
        else:
            return False

    gosi_conf = fields.Many2one('gosi.config', readonly=1) # default=lambda self: self.env['gosi.config'].search([],limit=1),  default=_default_gosi_config,


    # This function calculating values depends on the percentage in the gosi configuration (Contract > Configuration > Gosi Configuration)
    @api.depends('gosi_salary_amount','emp_type','gosi_conf.max_gosi_salary',
                 'gosi_conf.company_share_per','gosi_conf.company_share_per_non',
                 'gosi_conf.employee_share_per','gosi_conf.employee_share_per_non',)
    def _compute_share_amount(self):
        for line in self:
            # percentage = self.env['gosi.config'].search([],limit=1)
            percentage = line.gosi_conf
            if percentage:
                line.maximum_gosi_salary = percentage.max_gosi_salary
                line.company_share_per = 0
                line.employee_share_per = 0
                line.company_share_amount = 0
                line.employee_share_amount = 0
                if line.gosi_salary_amount > line.maximum_gosi_salary:
                    if line.emp_type == 'saudi':
                        if percentage.company_share_per > 0:
                            line.company_share_per = percentage.company_share_per
                            line.company_share_amount = (percentage.company_share_per / 100) * line.maximum_gosi_salary
                        if percentage.employee_share_per > 0:
                            line.employee_share_per = percentage.employee_share_per
                            line.employee_share_amount = (percentage.employee_share_per / 100) * line.maximum_gosi_salary
                    elif line.emp_type == 'not_saudi':
                        line.company_share_per = 0
                        line.employee_share_per = 0
                        if percentage.company_share_per_non > 0:
                            line.company_share_per = percentage.company_share_per_non
                            line.company_share_amount = (percentage.company_share_per_non / 100) * line.maximum_gosi_salary
                        if percentage.employee_share_per_non > 0:
                            line.employee_share_per = percentage.employee_share_per_non
                            line.employee_share_amount = (percentage.employee_share_per_non / 100) * line.maximum_gosi_salary

                else:
                    if line.emp_type == 'saudi':
                        if percentage.company_share_per > 0:
                            line.company_share_per = percentage.company_share_per
                            line.company_share_amount = (percentage.company_share_per / 100) * line.gosi_salary_amount
                        if percentage.employee_share_per > 0:
                            line.employee_share_per = percentage.employee_share_per
                            line.employee_share_amount = (percentage.employee_share_per / 100) * line.gosi_salary_amount
                    elif line.emp_type == 'not_saudi':
                        line.company_share_per = 0
                        line.employee_share_per = 0
                        if percentage.company_share_per_non > 0:
                            line.company_share_per = percentage.company_share_per_non
                            line.company_share_amount = (percentage.company_share_per_non / 100) * line.gosi_salary_amount
                        if percentage.employee_share_per_non > 0:
                            line.employee_share_per = percentage.employee_share_per_non
                            line.employee_share_amount = (percentage.employee_share_per_non / 100) * line.gosi_salary_amount

    @api.depends('wage','house_allowance_val')
    def _compute_gosi_salary(self):
        for line in self:
            line.gosi_salary_amount = line.wage + line.house_allowance_val

    ############## Allowances
    house_allowance_slc = fields.Selection([('percent','Percentage'),('amount','Amount')],string="Calculation")
    house_allowance_per = fields.Float(string="Percentage")
    house_allowance_val = fields.Monetary(string="House Amount")
    house_note = fields.Char(string='Note')
    is_house_per = fields.Boolean(store=True,compute='_house_allowance_func',)

    @api.depends('house_allowance_slc','house_allowance_per','wage')
    def _house_allowance_func(self):
        for line in self:
            line.is_house_per = False
            if line.house_allowance_slc == 'percent':
                line.is_house_per = True
                percentage = 0
                if line.house_allowance_per:
                    percentage = line.house_allowance_per / 100
                line.house_allowance_val = line.wage * percentage
            else:
                line.house_allowance_per = 0

    trans_allowance_slc = fields.Selection([('percent','Percentage'),('amount','Amount')],string="Calculation")
    trans_allowance_per = fields.Float(string="Percentage")
    trans_allowance_val = fields.Monetary(string="Transportation Amount")
    food_allowance_val = fields.Monetary(string="Food Amount")
    trans_note = fields.Char(string='Note')
    is_trans_per = fields.Boolean(store=True,compute='_trans_allowance_func',)

    @api.depends('trans_allowance_slc','trans_allowance_per','wage')
    def _trans_allowance_func(self):
        for line in self:
            line.is_trans_per = False
            if line.trans_allowance_slc == 'percent':
                line.is_trans_per = True
                percentage = 0
                if line.trans_allowance_per:
                    percentage = line.trans_allowance_per / 100
                line.trans_allowance_val = line.wage * percentage
            else:
                line.trans_allowance_per = 0

    other_allowance_slc = fields.Selection([('percent','Percentage'),('amount','Amount')],string="Calculation")
    other_allowance_per = fields.Float(string="Percentage")
    other_allowance_val = fields.Monetary(string="Other Amount", compute="_collect_allowances",store=True)
    other_note = fields.Char(string='Note')
    is_other_per = fields.Boolean(store=True,compute='_other_allowance_func',)

    total_package_val = fields.Monetary(string="Total", compute="_collect_total_package",store=True)

    @api.depends('other_allowance_val', 'house_allowance_val', 'trans_allowance_val', 'wage', 'food_allowance_val')
    def _collect_total_package(self):
        for rec in self:
            total_package = 0
            if rec.wage:
                total_package += rec.wage
            if rec.other_allowance_val:
                total_package += rec.other_allowance_val
            if rec.house_allowance_val:
                total_package += rec.house_allowance_val
            if rec.trans_allowance_val:
                total_package += rec.trans_allowance_val
            if rec.food_allowance_val:
                total_package += rec.food_allowance_val

            rec.total_package_val = total_package

    @api.depends('contract_allowances')
    def _collect_allowances(self):
        val = 0
        for line in self.contract_allowances:
            if line.is_paid:
                val += line.amount
        self.other_allowance_val = val

    @api.depends('other_allowance_slc','other_allowance_per','wage')
    def _other_allowance_func(self):
        for line in self:
            line.is_other_per = False
            if line.other_allowance_slc == 'percent':
                line.is_other_per = True
                percentage = 0
                if line.other_allowance_per:
                    percentage = line.other_allowance_per / 100
                line.other_allowance_val = line.wage * percentage
            else:
                line.other_allowance_per = 0

    car_allowance = fields.Monetary(string="Car Allowance")
    petrol_allowance = fields.Monetary(string="Petrol And Fuel Allowance")
    food_allowance = fields.Monetary(string="Food Allowance")
    calls_allowance = fields.Monetary(string="Calls Allowance")
    overtime_allowance = fields.Monetary(string="Overtime Allowance")
    work_nat_allowance = fields.Monetary(string="Work Nature Allowance")
    occ_haz_allowance = fields.Monetary(string="Occupational hazard Allowance")
    school_allowance = fields.Monetary(string="School Allowance")

    ############## Deduction
    other_ded_allowance = fields.Monetary(string="Other Deduction Allowance")

    ############## EOS
    eos_house_allowance_slc = fields.Selection([('percent','Percentage'),('amount','Amount')],string="Calculation")
    eos_house_allowance_per = fields.Float(string="Percentage")
    eos_house_allowance_val = fields.Monetary(string="EOS House Amount")
    eos_house_note = fields.Char(string='Note')
    is_eos_house_per = fields.Boolean(store=True,compute='_eos_house_allowance_func',)

    unpaid_house_amount = fields.Monetary(string="Unpaid House Amount")
    unpaid_transportation_amount = fields.Monetary(string="Unpaid Transportation Amount")

    @api.depends('eos_house_allowance_slc','eos_house_allowance_per','wage')
    def _eos_house_allowance_func(self):
        for line in self:
            line.is_eos_house_per = False
            if line.eos_house_allowance_slc == 'percent':
                line.is_eos_house_per = True
                percentage = 0
                if line.eos_house_allowance_per:
                    percentage = line.eos_house_allowance_per / 100
                line.eos_house_allowance_val = line.wage * percentage
            else:
                line.eos_house_allowance_per = 0

    eos_provision = fields.Float()
    eos_actually = fields.Float()
    eos_difference = fields.Float()
    change_date = fields.Date(string='تاريخ التغيير', readonly=True)
    eos_trans_allowance_slc = fields.Selection([('percent','Percentage'),('amount','Amount')],string="Calculation")
    eos_trans_allowance_per = fields.Float(string="Percentage")
    eos_trans_allowance_val = fields.Monetary(string="EOS Transportation Amount")
    eos_trans_note = fields.Char(string="Note")
    is_eos_trans_per = fields.Boolean(store=True,compute='_eos_trans_allowance_func',)

    @api.depends('eos_trans_allowance_slc','eos_trans_allowance_per','wage')
    def _eos_trans_allowance_func(self):
        for line in self:
            line.is_eos_trans_per = False
            if line.eos_trans_allowance_slc == 'percent':
                line.is_eos_trans_per = True
                percentage = 0
                if line.eos_trans_allowance_per:
                    percentage = line.eos_trans_allowance_per / 100
                line.eos_trans_allowance_val = line.wage * percentage
            else:
                line.eos_trans_allowance_per = 0

    eos_journal_id = fields.Many2one('account.journal', string='Journal')
    eos_debit_account = fields.Many2one('account.account', string='Debit Account', store=1, compute='_get_eos_account_value')
    eos_credit_account = fields.Many2one('account.account', string='Credit Account', store=1, compute='_get_eos_account_value')

    @api.depends('eos_journal_id')
    def _get_eos_account_value(self):
        for line in self:
            line.eos_debit_account = False
            line.eos_credit_account = False
            if line.eos_journal_id.type == 'general':
                line.eos_debit_account = line.eos_journal_id.gs_def_debit_acc.id
                line.eos_credit_account = line.eos_journal_id.gs_def_credit_acc.id
            elif line.eos_journal_id.type == 'cash' or line.eos_journal_id.type == 'bank':
                line.eos_debit_account = line.eos_journal_id.payment_debit_account_id.id
                line.eos_credit_account = line.eos_journal_id.payment_credit_account_id.id

    ############## Accrual Tickets
    tickets_no_company = fields.Integer(string="No. Of Tickets ")
    tickets_val_company = fields.Integer(string="Tickets Value")

    tickets_no_employee = fields.Integer(string="No. Of Tickets")
    tickets_val_employee = fields.Integer(string="Tickets Value")
    tickets_allowance = fields.Float(string="Tickets Allowance", default=0.0, store=True,)# compute='_tickets_allowance_amount'

    tickets_ids = fields.One2many('gs.tickets.line', 'contract_id', string='tickets', required=False)

    @api.onchange('tickets_ids')
    def _onchange_tickets_ids(self):
        for rec in self:
            rec.tickets_val_company = 0
            rec.tickets_val_employee = 0
            rec.tickets_no_company = 0
            rec.tickets_no_employee = 0
            for line in rec.tickets_ids:
                if line.paid_by_company:
                    rec.tickets_no_company += 1
                    rec.tickets_val_company += line.ticket_fare
                else:
                    rec.tickets_no_employee += 1
                    rec.tickets_val_employee += line.ticket_fare

    ticket_journal_id = fields.Many2one('account.journal', string='Journal')
    ticket_debit_account = fields.Many2one('account.account', string='Debit Account', store=1, compute='_get_ticket_account_value')
    ticket_credit_account = fields.Many2one('account.account', string='Credit Account', store=1, compute='_get_ticket_account_value')

    @api.depends('ticket_journal_id')
    def _get_ticket_account_value(self):
        for line in self:
            line.ticket_debit_account = False
            line.ticket_credit_account = False
            if line.ticket_journal_id.type == 'general':
                line.ticket_debit_account = line.ticket_journal_id.gs_def_debit_acc.id
                line.ticket_credit_account = line.ticket_journal_id.gs_def_credit_acc.id
            elif line.ticket_journal_id.type == 'cash' or line.ticket_journal_id.type == 'bank':
                line.ticket_debit_account = line.ticket_journal_id.payment_debit_account_id.id
                line.ticket_credit_account = line.ticket_journal_id.payment_credit_account_id.id

    # @api.depends('tickets_no','tickets_val')
    # def _tickets_allowance_amount(self):
    #     for line in self:
    #         line.tickets_allowance = line.tickets_no * line.tickets_val

    ############## Accrual Vacation

    vac_house_allowance_slc = fields.Selection([('percent','Percentage'),('amount','Amount')],string="Calculation")
    vac_house_allowance_per = fields.Float(string="Percentage")
    vac_house_allowance_val = fields.Monetary(string="VAC House Amount")
    vac_house_note = fields.Char(string='Note')
    is_vac_house_per = fields.Boolean(store=True,compute='_vac_house_allowance_func',)

    @api.depends('vac_house_allowance_slc','vac_house_allowance_per','wage')
    def _vac_house_allowance_func(self):
        for line in self:
            line.is_vac_house_per = False
            if line.vac_house_allowance_slc == 'percent':
                line.is_vac_house_per = True
                percentage = 0
                if line.vac_house_allowance_per:
                    percentage = line.vac_house_allowance_per / 100
                line.vac_house_allowance_val = line.wage * percentage
            else:
                line.vac_house_allowance_per = 0

    vac_trans_allowance_slc = fields.Selection([('percent','Percentage'),('amount','Amount')],string="Calculation")
    vac_trans_allowance_per = fields.Float(string="Percentage")
    vac_trans_allowance_val = fields.Monetary(string="VAC Transportation Amount")
    vac_trans_note = fields.Char(string='Note')
    is_vac_trans_per = fields.Boolean(store=True,compute='_vac_trans_allowance_func',)

    @api.depends('vac_trans_allowance_slc','vac_trans_allowance_per','wage')
    def _vac_trans_allowance_func(self):
        for line in self:
            line.is_vac_trans_per = False
            if line.vac_trans_allowance_slc == 'percent':
                line.is_vac_trans_per = True
                percentage = 0
                if line.vac_trans_allowance_per:
                    percentage = line.vac_trans_allowance_per / 100
                line.vac_trans_allowance_val = line.wage * percentage
            else:
                line.vac_trans_allowance_per = 0

    vacation_accrued = fields.Selection(string='Vacation Accrued', selection=[('monthly', 'Monthly'), ('yearly', 'Yearly')
                                                                            ,('every_2_years', 'Every 2 Years'), ],)
    vac_days = fields.Float(string="Annual Vacation Days")
    vac_days_per_month = fields.Float(string="Vacation Days Per Month")

    vac_journal_id = fields.Many2one('account.journal', string='Journal')
    vac_debit_account = fields.Many2one('account.account', string='Debit Account', store=1,compute='_get_vac_account_value')
    vac_credit_account = fields.Many2one('account.account', string='Credit Account', store=1, compute='_get_vac_account_value')

    @api.depends('vac_journal_id')
    def _get_vac_account_value(self):
        for line in self:
            line.vac_debit_account = False
            line.vac_credit_account = False
            if line.vac_journal_id.type == 'general':
                line.vac_debit_account = line.vac_journal_id.gs_def_debit_acc.id
                line.vac_credit_account = line.vac_journal_id.gs_def_credit_acc.id
            elif line.vac_journal_id.type == 'cash' or line.vac_journal_id.type == 'bank':
                line.vac_debit_account = line.vac_journal_id.payment_debit_account_id.id
                line.vac_credit_account = line.vac_journal_id.payment_credit_account_id.id


class AccountJournalInherit(models.Model):
    _inherit = 'account.journal'

    gs_def_debit_acc = fields.Many2one('account.account', string='Default Debit Account')
    gs_def_credit_acc = fields.Many2one('account.account', string='Default Credit Account')


class CollectAllowances(models.Model):
    _name = 'allowances.collect'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # allowance_type = fields.Selection([('eos','EOS'),('vacation','Vacation')])
    name = fields.Char('Field String',help="The Value Of This Field must be as the string of the allowance field")


class GsTicketsLine(models.Model):
    _name = 'gs.tickets.line'

    name = fields.Char(string='Name')
    employee_id = fields.Many2one('hr.employee', string="Employee",)
    follower_id = fields.Many2one('gs.follower', string='Follower')

    contract_id = fields.Many2one('hr.contract')
    type = fields.Selection(string='Type', selection=[('employee', 'Employee'), ('follower', 'Follower'), ], )
    country_id = fields.Many2one('res.country', 'Destination', tracking=True)
    ticket_type = fields.Selection(string='Ticket', selection=[('economy', 'Economy'), ('business', 'Business'), ], )
    ticket_fare = fields.Integer(string='Ticket Fare', )
    paid_by_company = fields.Boolean(string='Paid By Company')

    @api.onchange('type')
    def domain_type(self):
        return {'domain': {'follower_id': [('employee_id', '=', self.contract_id.employee_id.id)]}}

    @api.onchange('type', 'employee_id', 'follower_id')
    def _onchange_type(self):
        for rec in self:
            if rec.type == "employee":
                contract = self.env['hr.contract'].search([('state', '=', 'open'), ('employee_id', '=', rec.employee_id.id)], limit=1)
                if contract:
                    rec.country_id = rec.employee_id.country_id
                    # rec.ticket_type = contract.ticket_type
                    # rec.ticket_fare = contract.ticket_value
                    # rec.paid_by_company = contract.paid_by_company
            elif rec.type == "follower":
                rec.country_id = rec.follower_id.country_id
                # rec.ticket_type = rec.follower_id.ticket_type
                # rec.ticket_fare = rec.follower_id.ticket_value
                # rec.paid_by_company = rec.follower_id.paid_by_company

    @api.onchange('ticket_type', 'country_id')
    def _onchange_ticket_type(self):
        for rec in self:
            if rec.country_id:
                tickets = self.env['gs.tickets'].search([('country_id', '=', rec.country_id.id)], limit=1)
                if rec.ticket_type == 'economy':
                    self.ticket_fare = tickets.economy_fare
                if rec.ticket_type == 'business':
                    self.ticket_fare = tickets.business_class_fare

