# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_internal_transfer = fields.Boolean(string="Internal Transfer",
                                          readonly=False, store=True,
                                          tracking=True)
    destination_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Destination Journal',
        domain="[('type', 'in', ('bank','cash')), ('id', '!=', journal_id)]",
        check_company=True,
    )

    def _get_aml_default_display_name_list(self):
        """ Hook allowing custom values when constructing the default label to set on the journal items.

                :return: A list of terms to concatenate all together. E.g.
                    [
                        ('label', "Greg's Card"),
                        ('sep', ": "),
                        ('memo', "New Computer"),
                    ]
                """
        self.ensure_one()
        if self.is_internal_transfer:
            label = _("Internal Transfer")
        elif self.payment_method_line_id:
            label = self.payment_method_line_id.name
        else:
            label = _("No Payment Method")

        if self.memo:
            return [
                ('label', label),
                ('sep', ": "),
                ('memo', self.memo),
            ]
        return [
            ('label', label),
        ]

    def _get_liquidity_aml_display_name_list(self):
        """ Hook allowing custom values when constructing the label to set on the liquidity line.

        :return: A list of terms to concatenate all together. E.g.
            [('reference', "INV/2018/0001")]
        """
        self.ensure_one()
        if self.is_internal_transfer:
            if self.payment_type == 'inbound':
                return [('transfer_to', _('Transfer to %s', self.journal_id.name))]
            else: # payment.payment_type == 'outbound':
                return [('transfer_from', _('Transfer from %s', self.journal_id.name))]
        elif self.payment_reference:
            return [('reference', self.payment_reference)]
        else:
            return self._get_aml_default_display_name_list()

    @api.depends('partner_id', 'company_id', 'payment_type', 'destination_journal_id', 'is_internal_transfer')
    def _compute_available_partner_bank_ids(self):
        for pay in self:
            if pay.payment_type == 'inbound':
                pay.available_partner_bank_ids = pay.journal_id.bank_account_id
            elif pay.is_internal_transfer:
                pay.available_partner_bank_ids = pay.destination_journal_id.bank_account_id
            else:
                pay.available_partner_bank_ids = pay.partner_id.bank_ids \
                    .filtered(lambda x: x.company_id.id in (False, pay.company_id.id))._origin

    @api.depends('journal_id', 'is_internal_transfer')
    def _compute_partner_id(self):
        for pay in self:
            if pay.is_internal_transfer:
                pay.partner_id = pay.journal_id.company_id.partner_id
            elif pay.partner_id == pay.journal_id.company_id.partner_id:
                pay.partner_id = False
            else:
                pay.partner_id = pay.partner_id

    @api.depends('journal_id', 'partner_id', 'partner_type', 'is_internal_transfer', 'destination_journal_id')
    def _compute_destination_account_id(self):
        self.destination_account_id = False
        for pay in self:
            if pay.is_internal_transfer:
                pay.destination_account_id = pay.destination_journal_id.company_id.transfer_account_id
            elif pay.partner_type == 'customer':
                # Receive money from invoice or send money to refund it.
                if pay.partner_id:
                    pay.destination_account_id = pay.partner_id.with_company(
                        pay.company_id).property_account_receivable_id
                else:
                    pay.destination_account_id = self.env['account.account'].with_company(pay.company_id).search([
                        *self.env['account.account']._check_company_domain(pay.company_id),
                        ('account_type', '=', 'asset_receivable'),
                        ('deprecated', '=', False),
                    ], limit=1)
            elif pay.partner_type == 'supplier':
                # Send money to pay a bill or receive money to refund it.
                if pay.partner_id:
                    pay.destination_account_id = pay.partner_id.with_company(pay.company_id).property_account_payable_id
                else:
                    pay.destination_account_id = self.env['account.account'].with_company(pay.company_id).search([
                        *self.env['account.account']._check_company_domain(pay.company_id),
                        ('account_type', '=', 'liability_payable'),
                        ('deprecated', '=', False),
                    ], limit=1)

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        ''' Prepare the dictionary to create the default account.move.lines for the current payment.
        :param write_off_line_vals: Optional list of dictionaries to create a write-off account.move.line easily containing:
            * amount:       The amount to be added to the counterpart amount.
            * name:         The label to set on the line.
            * account_id:   The account on which create the write-off.
        :param force_balance: Optional balance.
        :return: A list of python dictionary to be passed to the account.move.line's 'create' method.
        '''
        self.ensure_one()
        write_off_line_vals = write_off_line_vals or []

        if not self.outstanding_account_id:
            raise UserError(_(
                "You can't create a new payment without an outstanding payments/receipts account set either on the company or the %(payment_method)s payment method in the %(journal)s journal.",
                payment_method=self.payment_method_line_id.name, journal=self.journal_id.display_name))

        # Compute amounts.
        write_off_line_vals_list = write_off_line_vals or []
        write_off_amount_currency = sum(x['amount_currency'] for x in write_off_line_vals_list)
        write_off_balance = sum(x['balance'] for x in write_off_line_vals_list)

        if self.payment_type == 'inbound':
            # Receive money.
            liquidity_amount_currency = self.amount
        elif self.payment_type == 'outbound':
            # Send money.
            liquidity_amount_currency = -self.amount
        else:
            liquidity_amount_currency = 0.0

        if not write_off_line_vals and force_balance is not None:
            sign = 1 if liquidity_amount_currency > 0 else -1
            liquidity_balance = sign * abs(force_balance)
        else:
            liquidity_balance = self.currency_id._convert(
                liquidity_amount_currency,
                self.company_id.currency_id,
                self.company_id,
                self.date,
            )
        counterpart_amount_currency = -liquidity_amount_currency - write_off_amount_currency
        counterpart_balance = -liquidity_balance - write_off_balance
        currency_id = self.currency_id.id

        # Compute a default label to set on the journal items.
        liquidity_line_name = ''.join(x[1] for x in self._get_liquidity_aml_display_name_list())
        counterpart_line_name = ''.join(x[1] for x in self._get_aml_default_display_name_list())

        line_vals_list = [
            # Liquidity line.
            {
                'name': liquidity_line_name,
                'date_maturity': self.date,
                'amount_currency': liquidity_amount_currency,
                'currency_id': currency_id,
                'debit': liquidity_balance if liquidity_balance > 0.0 else 0.0,
                'credit': -liquidity_balance if liquidity_balance < 0.0 else 0.0,
                'partner_id': self.partner_id.id,
                'account_id': self.outstanding_account_id.id,
            },
            # Receivable / Payable.
            {
                'name': counterpart_line_name,
                'date_maturity': self.date,
                'amount_currency': counterpart_amount_currency,
                'currency_id': currency_id,
                'debit': counterpart_balance if counterpart_balance > 0.0 else 0.0,
                'credit': -counterpart_balance if counterpart_balance < 0.0 else 0.0,
                'partner_id': self.partner_id.id,
                'account_id': self.destination_account_id.id,
            },
        ]
        return line_vals_list + write_off_line_vals_list

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        res = super()._get_trigger_fields_to_synchronize()
        res += ('is_internal_transfer',)
        return res

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default)
        for payment, vals in zip(self, vals_list):
            if not payment.is_internal_transfer:
                vals.update({
                    'journal_id': payment.journal_id.id,
                    'payment_method_line_id': payment.payment_method_line_id.id,
                    **(vals or {}),
                })
        return vals_list

    def action_post(self):
        ''' draft -> posted '''
        # Do not allow posting if the account is required but not trusted
        for payment in self:
            if payment.require_partner_bank_account and not payment.partner_bank_id.allow_out_payment:
                raise UserError(_(
                    "To record payments with %(method_name)s, the recipient bank account must be manually validated. "
                    "You should go on the partner bank account of %(partner)s in order to validate it.",
                    method_name=self.payment_method_line_id.name,
                    partner=payment.partner_id.display_name,
                ))
        # Avoid going back one state when clicking on the confirm action in the payment list view and having paid expenses selected
        # We need to set values to each payment to avoid recomputation later
        self.filtered(lambda pay: pay.state in {False, 'draft', 'in_process'}).state = 'in_process'

        self.filtered(
            lambda pay: pay.is_internal_transfer and not pay.paired_internal_transfer_payment_id
        )._create_paired_internal_transfer_payment()

    def _create_paired_internal_transfer_payment(self):
        ''' When an internal transfer is posted, a paired payment is created
        with opposite payment_type and swapped journal_id & destination_journal_id.
        Both payments liquidity transfer lines are then reconciled.
        '''
        for payment in self:
            payment_type = payment.payment_type == 'outbound' and 'inbound' or 'outbound'
            available_payment_method_lines = payment.destination_journal_id._get_available_payment_method_lines(payment_type)
            inbound_payment_method = payment.partner_id.property_inbound_payment_method_line_id
            outbound_payment_method = payment.partner_id.property_outbound_payment_method_line_id
            if payment.payment_type == 'outbound' and inbound_payment_method.id in available_payment_method_lines.ids:
                payment_method_line_id = inbound_payment_method
            elif payment.payment_type == 'inbound' and outbound_payment_method.id in available_payment_method_lines.ids:
                payment_method_line_id = outbound_payment_method
            elif payment.payment_method_line_id.id in available_payment_method_lines.ids:
                payment_method_line_id = payment.payment_method_line_id
            elif available_payment_method_lines:
                payment_method_line_id = available_payment_method_lines[0]._origin
            else:
                payment_method_line_id = False

            paired_payment = payment.copy({
                'journal_id': payment.destination_journal_id.id,
                'company_id': payment.company_id.id,
                'destination_journal_id': payment.journal_id.id,
                'payment_method_line_id': payment_method_line_id.id,
                'payment_type': payment_type,
                'move_id': None,
                'memo': payment.memo,
                'paired_internal_transfer_payment_id': payment.id,
                'date': payment.date,
            })
            paired_payment.action_post()
            payment.paired_internal_transfer_payment_id = paired_payment
            body = _("This payment has been created from:") + payment._get_html_link()
            paired_payment.message_post(body=body)
            body = _("A second payment has been created:") + paired_payment._get_html_link()
            payment.message_post(body=body)

            lines = (payment.move_id.line_ids + paired_payment.move_id.line_ids).filtered(
                lambda l: l.account_id == payment.destination_account_id and not l.reconciled)
            lines.reconcile()

    def action_open_destination_journal(self):
        ''' Redirect the user to this destination journal.
        :return:    An action on account.move.
        '''
        self.ensure_one()

        action = {
            'name': _("Destination journal"),
            'type': 'ir.actions.act_window',
            'res_model': 'account.journal',
            'context': {'create': False},
            'view_mode': 'form',
            'target': 'new',
            'res_id': self.destination_journal_id.id,
        }
        return action

