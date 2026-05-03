# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from datetime import datetime, date, timedelta
from odoo import models, fields, api, exceptions, _
from odoo.addons.test_convert.tests.test_env import record
from odoo.exceptions import ValidationError,UserError
import math
import logging

_logger = logging.getLogger(__name__)


class Settlement(models.TransientModel):
    _name = 'hr.benefit.settlement'

    def _default_debit_account_id(self):
        return self.env.user.company_id.debit_account_id

    def _default_expense_account_id(self):
        return self.env.user.company_id.expense_account_id

    def _default_expense_journal_id(self):
        return self.env.user.company_id.expense_journal_id

    def _default_settlement_journal_id(self):
        return self.env.user.company_id.settlement_journal_id

    request_id = fields.Many2one(comodel_name="hr.end.service.benefit")
    employee_id = fields.Many2one(comodel_name="hr.employee", related='request_id.employee_id')
    amount = fields.Float(related='request_id.amount')
    payment_amount = fields.Float('Amount', compute='_compute_amount', precompute=True, inverse='_inverse_amount', store=True)
    total_payslip_deserved_amount = fields.Float(related='request_id.total_payslip_deserved_amount')
    settlement_journal_id = fields.Many2one(comodel_name="account.journal", default=_default_settlement_journal_id)
    payment_date = fields.Date(string=" Payment Date", default=datetime.now().strftime('%Y-%m-%d'), )
    expense_account_id = fields.Many2one(comodel_name="account.account", default=_default_expense_account_id)
    expense_journal_id = fields.Many2one(comodel_name="account.journal", default=_default_expense_journal_id, )
    expense_date = fields.Date(string="Expense Date", default=datetime.now().strftime('%Y-%m-%d'), )
    payment_difference_show = fields.Boolean(compute='_compute_payment_difference_show')
    payment_difference = fields.Float(compute='_compute_payment_reference')
    payment_difference_handling = fields.Selection(
        string="Payment ",
        selection=[('open', 'Keep open'), ('reconcile', 'Mark as fully paid')],
        compute='_compute_payment_difference_handling',
        store=True,
        readonly=False,
    )
    inial_amount = fields.Float(compute='_compute_inial_amount', string='Total Entitlement')
    @api.depends('payment_difference')
    def _compute_payment_difference_handling(self):
        for record in self:
            if record.payment_difference == 0.0 :
                record.payment_difference_handling = 'reconcile'
            else:
                record.payment_difference_handling = 'open'
    @api.depends('amount', 'request_id', 'payment_amount')
    def _compute_payment_reference(self):
        for record in self:
            if record.payment_amount:
                record.payment_difference = record.inial_amount - record.payment_amount
            else:
                record.payment_difference = 0.0
    @api.depends('payment_difference')
    def _compute_payment_difference_show(self):
        for record in self:
            if record.payment_difference:
                if record.payment_difference != 0.0:
                    record.payment_difference_show = True
                else:
                    record.payment_difference_show = False
            else:
                record.payment_difference_show = False
    @api.depends('amount')
    def _compute_amount(self):
        for record in self:
            payments = self.env['account.payment'].search([('memo', '=', record.request_id.name)])
            record.payment_amount = record.amount - sum(payments.mapped('amount'))

    @api.depends('amount')
    def _compute_inial_amount(self):
        for record in self:
            payments = self.env['account.payment'].search([('memo', '=', record.request_id.name)])
            record.inial_amount = record.amount - sum(payments.mapped('amount'))

    @api.onchange('payment_amount')
    def _inverse_amount(self):
        for record in self:
            record.payment_amount = record.payment_amount

    # def settle_employee_reward(self):
    #     for record in self:
    #         if not record.employee_id.address_home_id:
    #             raise exceptions.ValidationError(
    #                 _("This employee has no private address,"
    #                   " please add it at employee profile !!"))
    #         # if not record.employee_id.address_home_id:
    #         #     raise exceptions.ValidationError(
    #         #         _("This employee private address is not a supplier, please mark it as a supplier!!"))
    #         if not record.employee_id.address_home_id.property_account_payable_id:
    #             raise exceptions.ValidationError(
    #                 _("This employee has no payable account at private address,"
    #                   " please add it at employee private address partner !!"))
    #         # Journal Entry Creation
    #         line_ids = []
    #         name = _('Ending service reward settlement of %s') % (record.employee_id.name)
    #         move_dict = {
    #             'narration': name,
    #             'ref': name,
    #             'journal_id': record.expense_journal_id.id,
    #             'date': record.expense_date,
    #         }
    #         amount = record.amount
    #         total_payslip_deserved_amount = record.total_payslip_deserved_amount
    #         debit_account_id = record.expense_account_id.id
    #         credit_account_id = record.employee_id.address_home_id.property_account_payable_id.id
    #         if debit_account_id and record.employee_id.address_home_id:
    #             debit_line = (0, 0, {
    #                 'name': name + str(' debit line'),
    #                 'partner_id': record.employee_id.address_home_id.id,
    #                 'account_id': debit_account_id,
    #                 'journal_id': record.expense_journal_id.id,
    #                 'date': record.expense_date,
    #                 'debit': amount > 0.0 and amount or 0.0,
    #                 'credit': amount < 0.0 and -amount or 0.0,
    #             })
    #             line_ids.append(debit_line)
    #         if credit_account_id:
    #             credit_line = (0, 0, {
    #                 'name': name + str(' credit line'),
    #                 'partner_id': record.employee_id.address_home_id.id,
    #                 'account_id': credit_account_id,
    #                 'journal_id': record.expense_journal_id.id,
    #                 'date': record.expense_date,
    #                 'debit': amount < 0.0 and -amount or 0.0,
    #                 'credit': amount > 0.0 and amount or 0.0,
    #             })
    #             line_ids.append(credit_line)
    #         move_dict['line_ids'] = line_ids
    #         move = self.env['account.move'].with_context(check_move_validity=False).create([move_dict])
    #         move.action_post()
    #
    #         # Payment Creation
    #         name = _('Ending service reward payment of %s') % (record.employee_id.name)
    #         payment_dict = {
    #             # 'communication': name,
    #             'reward_id': record.request_id.id,
    #             'payment_type': 'outbound',
    #             'partner_type': 'supplier',
    #             'amount': record.amount,
    #             'journal_id': record.settlement_journal_id.id,
    #             'partner_id': record.employee_id.address_home_id.id,
    #             # 'payment_method_line_id': record.settlement_journal_id.outbound_payment_method_line_ids[0].id,
    #             'date': record.payment_date,
    #         }
    #         payment_id = self.env['account.payment'].create(payment_dict)
    #         payment_id.action_post()
    #         if record.total_payslip_deserved_amount > 0:
    #             # payslip_name = _('Ending service payslip payment of %s') % (record.employee_id.name)
    #             # payslip_payment_dict = {
    #             #     # 'communication': name,
    #             #     'reward_id': record.request_id.id,
    #             #     'payment_type': 'outbound',
    #             #     'partner_type': 'supplier',
    #             #     'amount': record.total_payslip_deserved_amount,
    #             #     'journal_id': record.settlement_journal_id.id,
    #             #     'partner_id': record.employee_id.address_home_id.id,
    #             #     'payment_method_line_id': record.settlement_journal_id.outbound_payment_method_line_ids[0].id,
    #             #     'date': record.payment_date,
    #             # }
    #             # payslip_payment_id = self.env['account.payment'].create(payslip_payment_dict)
    #             # payslip_payment_id.action_post()
    #             # record.request_id.write(
    #             #     {'account_move_id': move.id, 'payment_id': payment_id.id,
    #             #      'payslip_payment_id': payslip_payment_id.id, 'state': 'paid'})
    #             pass
    #         else:
    #             record.request_id.write(
    #                 {'account_move_id': move.id, 'payment_id': payment_id.id, 'state': 'paid'})
    def settle_employee_reward_emp(self):
        """Function to create a balanced account.move (journal entry) for the settlement."""
        for record in self:
            if not record.employee_id.address_home_id:
                raise exceptions.ValidationError(
                    _("This employee has no private address,"
                      " please add it at employee profile !!"))
            # if not record.employee_id.address_home_id:
            #     raise exceptions.ValidationError(
            #         _("This employee private address is not a supplier, please mark it as a supplier!!"))
            if not record.employee_id.address_home_id.property_account_payable_id:
                raise exceptions.ValidationError(
                    _("This employee has no payable account at private address,"
                      " please add it at employee private address partner !!"))
            # Journal Entry Creation
            line_ids = []
            name = _('Ending service reward settlement of %s') % (record.employee_id.name)
            move_dict = {
                'narration': name,
                'ref': name,
                'journal_id': record.expense_journal_id.id,
                'date': record.expense_date,
            }
            # amount = record.amount
            total_payslip_deserved_amount = record.total_payslip_deserved_amount
            debit_account_id = record.expense_account_id.id
            print(debit_account_id , "gggggggggggggggggggggggggggggg")
            credit_account_id = record.employee_id.address_home_id.property_account_payable_id.id

            for line in self.request_id.allows_ids:
                if not line.type_allowances.account:
                    raise UserError(_("Account for type allowances not found."))
                line_ids.append((0, 0, {
                    'account_id': line.type_allowances.account.id,
                    'partner_id': self.employee_id.address_home_id.id,
                    'analytic_distribution': {record.request_id.analytic_account_id.id:100} if record.request_id.analytic_account_id else False,
                    'name': line.other_allowances_note,
                    'debit': line.other_allowances,
                    'credit': 0,
                }))

            for line in self.request_id.deduct_ids:
                if not line.type_detuction.account:
                    raise UserError(_("Account for type deduction not found."))
                line_ids.append((0, 0, {
                    'account_id': line.type_detuction.account.id,
                    'partner_id': self.employee_id.address_home_id.id,
                    'name': line.detuction_note,
                    'debit': 0,
                    'analytic_distribution': {
                        record.request_id.analytic_account_id.id: 100} if record.request_id.analytic_account_id else False,

                    'credit': line.detuction,
                }))

            # Adding amount_due to the journal entry
            amount_due = self.request_id.total_holiday_deserved_amount
            eos_vacation = self.env['type.allowances'].search([('eos_vacation', '=', True)], limit=1)
            if not eos_vacation or not eos_vacation.account:
                raise ValidationError(_('Please Add Account To Eos Vacation in Type Allowance'))

            line_ids.append((0, 0, {
                'account_id': eos_vacation.account.id,
                'partner_id': self.employee_id.address_home_id.id,
                'name': _("Vacation Amount"),
                'debit': amount_due,
                'analytic_distribution': {
                    record.request_id.analytic_account_id.id: 100} if record.request_id.analytic_account_id else False,

                'credit': 0,
            }))
            # Add ticket to the journal entry

            if self.request_id.payslip_ids:
                payroll_account = self.env['type.allowances'].search([('is_payroll', '=', True)], limit=1)
                if not payroll_account or not payroll_account.account:
                    raise ValidationError(_('Please Add Account To Payroll in Type Allowance'))
                line_ids.append((0, 0, {
                    'account_id': payroll_account.account.id,
                    'partner_id': self.employee_id.address_home_id.id,
                    'name': _("Payroll"),
                    'debit': self.total_payslip_deserved_amount,
                    'analytic_distribution': {
                        record.request_id.analytic_account_id.id: 100} if record.request_id.analytic_account_id else False,

                    'credit': 0,
                }))
            if self.request_id.total_deserved_amount:
                if not self.env.company.eos_indemnity_account_id:
                    raise UserError(_("Account for Eos Indemnity account not found."))

                line_ids.append((0, 0, {
                    'account_id': self.env.company.eos_indemnity_account_id.id,
                    'partner_id': self.employee_id.address_home_id.id,
                    'name': _("EOS Idemnity"),
                    'debit':self.request_id.total_deserved_amount,
                    'analytic_distribution': {
                        record.request_id.analytic_account_id.id: 100} if record.request_id.analytic_account_id else False,

                    'credit': 0,
                }))
            if debit_account_id and record.employee_id.address_home_id:
                debit_line = (0, 0, {
                    'name': name + str(' debit line'),
                    'partner_id': record.employee_id.address_home_id.id,
                    'account_id': debit_account_id,
                    'journal_id': record.expense_journal_id.id,
                    'analytic_distribution': {
                        record.request_id.analytic_account_id.id: 100} if record.request_id.analytic_account_id else False,

                    'date': record.expense_date,
                    'debit': 0,
                    'credit': self.amount,
                })
                print("vvvvvvvvvvvvvvvvvvvvvvvv")
                line_ids.append(debit_line)

            move_dict['line_ids'] = line_ids
            move = self.env['account.move'].with_context(check_move_validity=False).create([move_dict])
            record.request_id.write(
                            {'account_move_id': move.id})
            #         move.action_post()



    def settle_employee_reward(self):
        """Function to create the account.payment (payment entry) and update state."""
        for record in self:
            if record.payment_amount <= 0.0:
                raise ValidationError('Not Amount To Payment')
            if record.payment_difference < 0.0:
                raise ValidationError('not allow to pay more than Total Entitlement')
            if not record.employee_id.address_home_id:
                raise exceptions.ValidationError(
                    _("This employee has no private address, please add it to the employee profile!"))

            # Create payment entry (account.payment)
            name = _('Ending service reward payment of %s') % (record.employee_id.name)
            payment_dict = {
                'reward_id': record.request_id.id,
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'amount': record.payment_amount,
                'journal_id': record.settlement_journal_id.id,
                'partner_id': record.employee_id.address_home_id.id,
                'date': record.payment_date,
                'memo': self.request_id.name,
                'destination_account_id': self.env.user.company_id.expense_account_id.id,
            }
            payment_id = self.env['account.payment'].create(payment_dict)
            payment_id.action_post()
            if record.payment_difference_handling == 'reconcile':
               record.request_id.write({'payment_id': payment_id.id, 'state': 'paid', 'paid_status': 'paid'})
            if record.payment_difference_handling == 'open':
                record.request_id.write({'payment_id': payment_id.id, 'paid_status': 'partial'})


class Payment(models.Model):
    _name = 'account.payment'
    _inherit = 'account.payment'

    reward_id = fields.Many2one(comodel_name="hr.end.service.benefit", string="", required=False, )

    # def action_post(self):
    #     res = super(Payment, self).action_post()
    #     for record in self:
    #         record.reward_id.state = 'paid'
    #     return res

    def name_get(self):
        new_format = []
        for rec in self:
            if rec.name:
                result = rec.name
            else:
                result = rec.partner_id.name + ' Payment'
            new_format.append((rec.id, result))
        return new_format
    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        res = super()._prepare_move_line_default_vals(write_off_line_vals,force_balance)
        if self.reward_id:
            print('resAhmed', res)
            for rec in res:
                rec.update({
                    'analytic_distribution': {self.reward_id.analytic_account_id.id:100} if self.reward_id.analytic_account_id else False,
                })
        return res
