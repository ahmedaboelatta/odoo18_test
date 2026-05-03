# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError


class GsGetDataWizard(models.TransientModel):
    _name = "register.payment.wizard"

    company_id = fields.Many2one('res.company', store=True, copy=False, default=lambda self: self.env.company.id)
    journal_id = fields.Many2one('account.journal', store=True, readonly=False,
                                 domain="[('company_id', '=', company_id), ('type', 'in', ('bank', 'cash'))]")
    account_id = fields.Many2one('account.account', string="Account")
    partner_bank_id = fields.Many2one(comodel_name='res.partner.bank', string="Recipient Bank Account", readonly=False,
                                      store=True, )
    currency_id = fields.Many2one('res.currency', string='Currency', store=True, readonly=False,
                                  compute='_compute_currency_id',
                                  help="The payment's currency.")
    amount = fields.Monetary(currency_field='currency_id', store=True, readonly=False, )
    payment_date = fields.Date(string="Payment Date", required=True, default=fields.Date.context_today)
    communication = fields.Char(string="Memo", store=True, readonly=False)
    payslip_ids = fields.Many2many('hr.payslip', string='Payslip')
    bol_field = fields.Boolean()

    @api.depends('journal_id')
    def _compute_currency_id(self):
        for wizard in self:
            wizard.currency_id = wizard.journal_id.currency_id or wizard.company_id.currency_id

    @api.onchange('amount')
    def _onchange_amount(self):
        for rec in self:
            if rec.amount:
                active_id = self._context.get('active_ids') or self._context.get('active_id')
                payslips = self.env['hr.payslip'].browse(active_id)
                for payslip in payslips:
                    if rec.amount > payslip.net_wage:
                        raise UserError(_("Amount bigger than net wage"))

    @api.onchange('payment_date')
    def _compute_communication(self):
        active_id = self._context.get('active_ids') or self._context.get('active_id')
        payslip = self.env['hr.payslip'].browse(active_id)
        if len(payslip) > 1:
            self.bol_field = True
        else:
            self.communication = payslip.number
            self.amount = payslip.net_wage
            self.journal_id = payslip.journal_id

    # def action_register_payment(self):
    #     active_id = self._context.get('active_ids') or self._context.get('active_id')
    #     payslips = self.env['hr.payslip'].browse(active_id)
    #
    #     action = {
    #         'name': _('Journal Entries'),
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'account.move',
    #         'context': {'create': False},
    #     }
    #     vals = {}
    #     debit_vals = []
    #     credit_vals = []
    #     values = []
    #     net_wage = 0
    #     for payslip in payslips:
    #         if payslip.payment_state == 'in_payment':
    #             raise UserError(_("You can't register a payment because you have request in payment"))
    #         else:
    #             debit_vals.append((0, 0, {
    #                 'name': payslip.name,
    #                 'account_id': self.account_id.id,
    #                 'partner_id': payslip.employee_id.address_home_id.id,
    #                 'debit': payslip.net_wage,
    #                 'credit': 0.0,
    #             }))
    #             vals.update({
    #                 'ref': 'Employee payroll',
    #                 'journal_id': self.journal_id.id,
    #                 'date': self.payment_date,
    #             })
    #             values.append(vals)
    #             payslip.payment_state = 'in_payment'
    #             net_wage += payslip.net_wage
    #     credit_vals.append((0, 0, {
    #         'account_id': self.journal_id.default_account_id.id,
    #         'debit': 0.0,
    #         'credit': net_wage,
    #     }))
    #     vals.update({
    #         'line_ids': [debit_vals, credit_vals]
    #
    #     })
    #     print("vals", vals)
    #     entry = self.env['account.move'].create(values)
    #     if len(payslips) == 1:
    #         action.update({
    #             'view_mode': 'form',
    #             'res_id': entry.id,
    #         })
    #     else:
    #         action.update({
    #             'view_mode': 'tree,form',
    #             'domain': [('id', 'in', entry.ids)],
    #         })
    #     return action

    def action_register_payment(self):
        active_id = self._context.get('active_ids') or self._context.get('active_id')
        payslips = self.env['hr.payslip'].browse(active_id)

        vals = {
            'ref': 'Employee payroll',
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
        }
        entry = self.env['account.move'].create(vals)
        if entry:
            net_wage = 0
            sum_wage = 0
            for payslip1 in payslips:
                net_wage += payslip1.net_wage
            lst = []
            debit_name = 0
            if self.journal_id.inbound_payment_method_line_ids:
                for jor in self.journal_id.inbound_payment_method_line_ids:
                    if jor.payment_account_id:
                        debit_name = jor.payment_account_id.id

            journal_name = 0
            if self.journal_id.outbound_payment_method_line_ids:
                for jor in self.journal_id.outbound_payment_method_line_ids:
                    if jor.payment_account_id:
                        journal_name = jor.payment_account_id.id
            else:
                journal_name = self.journal_id.default_account_id.id

            for payslip in payslips:
                payslip.gs_journal_entries_id = entry.id
                entry.gs_payslip_ids = [(4, payslip.id)]
                if payslip.payment_state == 'in_payment':
                    raise UserError(_("You can't register a payment because you have request in payment"))
                else:
                    val = (0, 0, {
                        'name': payslip.name,
                        'account_id': self.account_id.id,
                        'partner_id': payslip.employee_id.address_home_id.id,
                        'debit': payslip.net_wage,
                        'credit': 0.0,
                    })
                    lst.append(val)
                    sum_wage += payslip.net_wage
                    if sum_wage == net_wage:
                        val = (0, 0, {
                            'account_id': journal_name,
                            'debit': 0.0,
                            'credit': net_wage,
                        })
                        lst.append(val)
                    if self.journal_id.default_account_id.id == debit_name or self.journal_id.default_account_id.id == journal_name:
                        payslip.payment_state = 'paid'
                    else:
                        payslip.payment_state = 'in_payment'
            entry.line_ids = lst
            entry.state = 'posted'
        action = {
            'name': _('Journal Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': entry.id,
            'context': {'create': False},
        }
        return action
