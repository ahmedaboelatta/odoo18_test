# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
from datetime import date, datetime, time
import calendar


class GsEmployeeInherit(models.Model):
    _inherit = 'hr.employee'
    @api.model
    def create(self, vals):
        # if vals.get('registration_number2', _('New')) == _('New'):
        #     vals['registration_number2'] = self.env['ir.sequence'].next_by_code('registration_number_code') or _('New')
        if vals.get('bank_account_id'):
            vals['is_bank_account'] = True
        res = super(GsEmployeeInherit, self).create(vals)
        return res
    is_bank_account = fields.Boolean()
    is_has_group = fields.Boolean(compute='_compute_has_group')

    def _compute_has_group(self):
        if not self.env.user.has_group('account.group_account_manager'):
            self.is_has_group = True
        else:
            self.is_has_group = False

    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    total_package_val = fields.Monetary(string="Total", )
    wage = fields.Monetary('Basic Salary', tracking=True, help="Employee's monthly gross wage.")
    house_allowance_val = fields.Monetary(string="House Amount")
    trans_allowance_val = fields.Monetary(string="Transportation Amount")
    contract_allowances = fields.One2many('hr.contract.allowance', 'employee_id')
    eos_total_amount = fields.Monetary('EOS Base Amount', )
    eos_total_amount_month = fields.Monetary('EOS Monthly', compute='_compute_action_get_data')
    vacation_total_amount = fields.Monetary('Vacation Base Amount')
    vacation_total_amount_month = fields.Monetary('Vacation Monthly', compute='_compute_get_amount_month')
    run_compute = fields.Boolean(compute="_compute_action_get_data")
    total_paid = fields.Monetary(string="Total Paid")
    other_allowance = fields.Monetary(string="Other Allowance")
    ticket_base_amount = fields.Monetary(string="Ticket Base Amount")
    ticket_base_amount_month = fields.Monetary(string="Ticket Monthly", compute='_compute_get_amount_month')
    no_of_tickets = fields.Integer(string="No Of Tickets")
    annual_time_off_accrued = fields.Integer(string="Annual Time Off Accrued")
    medical_insurance_cost = fields.Integer(string="Medical insurance cost")

    employee_gosi_saudi = fields.Monetary(string="Employee Gosi (Saudi)")
    net_salary = fields.Monetary(string="Net Salary", compute='_get_net_salary')

    vacation_premium = fields.Monetary(string="Vacation Premium", compute='_get_vacation_premium')
    eos_premium = fields.Monetary(string="EOS Premium", compute='_get_eos_premium')
    ticket_premium = fields.Monetary(string="Ticket Premium", compute='_get_ticket_premium')
    iqama_renew_premium = fields.Monetary(string="Iqama Renew Premium")
    medical_insurance = fields.Monetary(string="Medical Insurance")
    gosi_company_share = fields.Monetary(string="Gosi Company Share", compute='_get_gosi_company_share')
    total_unpaid = fields.Monetary(string="Total Unpaid", compute='_get_total_unpaid')
    total_monthly_cost = fields.Monetary(string="Total Monthly Cost", compute='_get_total_monthly_cost')

    children = fields.Integer(string='Number of Followers', compute="_children_count")

    unpaid_house_amount = fields.Monetary(string="Unpaid House Amount", compute='_compute_action_get_data')
    unpaid_transportation_amount = fields.Monetary(string="Unpaid Transportation Amount",
                                                   compute='_compute_action_get_data')
    unpaid_other_allowances = fields.Monetary(string="Unpaid Other Allowances", compute='_compute_action_get_data')
    is_gosi = fields.Boolean(string='Is Gosi?', default=True)
    registration_number2 = fields.Char('Number of the Employee', copy=False,
                                      required=True,
                                      index=True
                                      )
    food_allowance_val = fields.Monetary(string="Food Amount", related="contract_id.food_allowance_val")

    # @api.onchange('is_gosi')
    # def _onchange_is_gosi(self):
    #     for rec in self:
    #         if not rec.is_gosi:
    #             rec.total_paid -= rec.employee_gosi_saudi

    @api.onchange('job_id')
    def _onchange_job_id(self):
        for rec in self:
            if rec.job_id:
                rec.contract_id.job_id = rec.job_id.id
                rec.job_title = rec.job_id.name

    def _get_total_monthly_cost(self):
        for rec in self:
            rec.total_monthly_cost = rec.total_paid + rec.total_unpaid

    def _compute_get_amount_month(self):
        for rec in self:
            rec.vacation_total_amount_month = rec.vacation_total_amount / 12
            rec.ticket_base_amount_month = rec.ticket_base_amount / 12

    def _get_total_unpaid(self):
        for rec in self:
            rec.total_unpaid = rec.ticket_base_amount_month + rec.eos_total_amount_month + rec.vacation_total_amount_month + rec.iqama_renew_premium + \
                               rec.medical_insurance + rec.gosi_company_share + rec.unpaid_house_amount + rec.unpaid_transportation_amount + rec.unpaid_other_allowances

    def _get_gosi_company_share(self):
        for rec in self:
            contract = self.env['hr.contract'].search(
                [('state', 'in', ['draft', 'open']), ('employee_id', '=', rec.id)], limit=1)
            if contract:
                rec.gosi_company_share = rec.company_share_amount
            else:
                rec.gosi_company_share = 0

    def _get_ticket_premium(self):
        for rec in self:
            rec.ticket_premium = round(rec.ticket_base_amount / 11)

    def _get_net_salary(self):
        for rec in self:
            if rec.is_gosi:
                rec.net_salary = rec.total_paid - rec.employee_gosi_saudi
            else:
                rec.net_salary = rec.total_paid

    def action_set_gosi(self):
        employees = self.env['hr.employee'].search([('is_gosi', '=', False)])
        for emp in employees:
            emp.is_gosi = True

    def _get_eos_premium(self):
        for test in self:
            contract = self.env['hr.contract'].search(
                [('state', 'in', ['draft', 'open']), ('employee_id', '=', test.id)], limit=1)
            rd = relativedelta(date.today(), contract.date_start)
            year = rd.years
            month = rd.months
            day = rd.days
            if year < 5:
                test.eos_premium = round((test.eos_total_amount / 2) / 12)
            if year >= 5:
                test.eos_premium = round(test.eos_total_amount / 12)

    def _get_vacation_premium(self):
        for rec in self:
            rec.vacation_premium = round(((rec.vacation_total_amount / 30) * rec.annual_time_off_accrued) / 11)

    def _children_count(self):
        for each in self:
            followers = self.env['gs.follower'].search([('employee_id', '=', each.id)])
            each.children = len(followers)

    def _compute_action_get_data(self):
        for rec in self:
            rec.total_paid = 0
            rec.unpaid_other_allowances = 0
            rec.run_compute = True
            contract = self.env['hr.contract'].search(
                [('state', 'in', ['draft', 'open']), ('employee_id', '=', rec.id)], limit=1)
            if contract:
                contract._onchange_eos_total_amount()
                contract._onchange_collect_eos_allowances()
                contract._onchange_collect_vacation_allowances()
                contract._onchange_tickets_ids()

                rec.currency_id = contract.currency_id
                # rec.total_package_val = contract.total_package_val
                rec.wage = contract.wage
                rec.eos_total_amount = contract.eos_total_amount
                rec.eos_total_amount_month = contract.eos_total_amount_month
                rec.vacation_total_amount = contract.vacation_total_amount
                rec.ticket_base_amount = contract.tickets_val_company
                rec.no_of_tickets = contract.tickets_no_company
                rec.other_allowance = contract.other_allowance_val
                rec.annual_time_off_accrued = contract.vac_days
                rec.iqama_renew_premium = contract.iqama_renew_premium
                rec.medical_insurance = contract.medical_insurance
                rec.employee_gosi_saudi = rec.employee_share_amount
                rec.unpaid_house_amount = contract.unpaid_house_amount
                rec.unpaid_transportation_amount = contract.unpaid_transportation_amount

                for lin in contract.contract_allowances:
                    if not lin.is_paid:
                        rec.unpaid_other_allowances = lin.amount

                if contract.is_paid_trans:
                    rec.trans_allowance_val = contract.trans_allowance_val
                else:
                    rec.trans_allowance_val = 0
                if contract.is_paid_housing:
                    rec.house_allowance_val = contract.house_allowance_val
                else:
                    rec.house_allowance_val = 0

                lines = [(5, 0, 0)]
                for line in contract.contract_allowances:
                    val = {
                        'allowance_id': line.allowance_id.id,
                        'amount': line.amount,
                        'is_paid': line.is_paid,
                    }
                    lines.append((0, 0, val))
                    rec.contract_allowances = lines

                if rec.wage:
                    rec.total_paid += rec.wage
                if rec.trans_allowance_val:
                    rec.total_paid += rec.trans_allowance_val
                if rec.house_allowance_val:
                    rec.total_paid += rec.house_allowance_val
                if rec.other_allowance:
                    rec.total_paid += rec.other_allowance
                # if rec.employee_share_amount:
                #     if rec.is_gosi:
                #         rec.total_paid += rec.employee_share_amount
            else:
                rec.contract_allowances = [(5, 0, 0)]
                rec.wage = 0
                rec.eos_total_amount = 0
                rec.eos_total_amount_month = 0
                rec.vacation_total_amount = 0
                rec.ticket_base_amount = 0
                rec.no_of_tickets = 0
                rec.other_allowance = 0
                rec.annual_time_off_accrued = 0
                rec.employee_gosi_saudi = 0
                rec.trans_allowance_val = 0
                rec.house_allowance_val = 0
                rec.total_paid = 0
                rec.unpaid_house_amount = 0
                rec.unpaid_transportation_amount = 0
                rec.unpaid_other_allowances = 0
                rec.iqama_renew_premium = 0
                rec.medical_insurance = 0

    def action_refresh(self):
        for rec in self:
            rec.total_paid = 0
            rec.unpaid_other_allowances = 0
            rec.run_compute = True
            contract = self.env['hr.contract'].search(
                [('state', 'in', ['draft', 'open']), ('employee_id', '=', rec.id)], limit=1)
            if contract:
                contract._onchange_eos_total_amount()
                contract._onchange_collect_eos_allowances()
                contract._onchange_collect_vacation_allowances()
                contract._onchange_tickets_ids()

                rec.currency_id = contract.currency_id
                # rec.total_package_val = contract.total_package_val
                rec.wage = contract.wage
                rec.eos_total_amount = contract.eos_total_amount
                rec.eos_total_amount_month = contract.eos_total_amount_month
                rec.vacation_total_amount = contract.vacation_total_amount
                rec.ticket_base_amount = contract.tickets_val_company
                rec.no_of_tickets = contract.tickets_no_company
                rec.other_allowance = contract.other_allowance_val
                rec.annual_time_off_accrued = contract.vac_days
                rec.iqama_renew_premium = contract.iqama_renew_premium
                rec.medical_insurance = contract.medical_insurance
                rec.employee_gosi_saudi = rec.employee_share_amount
                rec.unpaid_house_amount = contract.unpaid_house_amount
                rec.unpaid_transportation_amount = contract.unpaid_transportation_amount

                for lin in contract.contract_allowances:
                    if not lin.is_paid:
                        rec.unpaid_other_allowances = lin.amount

                if contract.is_paid_trans:
                    rec.trans_allowance_val = contract.trans_allowance_val
                else:
                    rec.trans_allowance_val = 0
                if contract.is_paid_housing:
                    rec.house_allowance_val = contract.house_allowance_val
                else:
                    rec.house_allowance_val = 0

                lines = [(5, 0, 0)]
                for line in contract.contract_allowances:
                    val = {
                        'allowance_id': line.allowance_id.id,
                        'amount': line.amount,
                        'is_paid': line.is_paid,
                    }
                    lines.append((0, 0, val))
                    rec.contract_allowances = lines

                if rec.wage:
                    rec.total_paid += rec.wage
                if rec.trans_allowance_val:
                    rec.total_paid += rec.trans_allowance_val
                if rec.house_allowance_val:
                    rec.total_paid += rec.house_allowance_val
                if rec.other_allowance:
                    rec.total_paid += rec.other_allowance
                # if rec.employee_share_amount:
                #     if rec.is_gosi:
                #         rec.total_paid += rec.employee_share_amount
            else:
                rec.contract_allowances = [(5, 0, 0)]
                rec.wage = 0
                rec.eos_total_amount = 0
                rec.eos_total_amount_month = 0
                rec.vacation_total_amount = 0
                rec.ticket_base_amount = 0
                rec.no_of_tickets = 0
                rec.other_allowance = 0
                rec.annual_time_off_accrued = 0
                rec.employee_gosi_saudi = 0
                rec.trans_allowance_val = 0
                rec.house_allowance_val = 0
                rec.total_paid = 0
                rec.unpaid_house_amount = 0
                rec.unpaid_transportation_amount = 0
                rec.unpaid_other_allowances = 0

    def action_get_data(self):
        for rec in self:
            contract = self.env['hr.contract'].search(
                [('state', 'in', ['draft', 'open']), ('employee_id', '=', rec.id)], limit=1)
            rec.currency_id = contract.currency_id
            rec.total_package_val = contract.total_package_val
            rec.wage = contract.wage
            rec.house_allowance_val = contract.house_allowance_val
            rec.trans_allowance_val = contract.trans_allowance_val
            rec.eos_total_amount = contract.eos_total_amount
            rec.eos_total_amount_month = contract.eos_total_amount_month
            rec.vacation_total_amount = contract.vacation_total_amount

            lines = [(5, 0, 0)]
            for line in contract.contract_allowances:
                val = {
                    'allowance_id': line.allowance_id.id,
                    'amount': line.amount,
                    'is_paid': line.is_paid,
                }
                lines.append((0, 0, val))
                rec.contract_allowances = lines
