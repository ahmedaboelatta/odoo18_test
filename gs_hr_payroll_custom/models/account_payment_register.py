from odoo import models, fields, api


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    payslip_id = fields.Many2one('hr.payslip')

    def action_create_payments(self):
        res = super().action_create_payments()
        if self.payslip_id:
            self.payslip_id.state = 'paid'
        return res