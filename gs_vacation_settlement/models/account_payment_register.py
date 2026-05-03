from odoo import models, fields, api


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    hr_vacation_id = fields.Many2one('employee.vacation.settlement')

    def action_create_payments(self):
        res = super().action_create_payments()
        if self.hr_vacation_id:
            if round(self.amount,2) == round(self.hr_vacation_id.total_total,2):
                self.hr_vacation_id.write({'state':'pay'})
            else:
                if  not self.show_payment_difference:
                    self.hr_vacation_id.state = 'pay'
                    self.hr_vacation_id.paid_status = 'paid'
                else:
                    if self.payment_difference_handling == 'reconcile':
                        self.hr_vacation_id.state = 'pay'
                        self.hr_vacation_id.paid_status = 'paid'
                    if self.payment_difference_handling == 'open':
                        self.hr_vacation_id.paid_status = 'partial'
        return res

    def _create_payment_vals_from_wizard(self, batch_result):
        res = super()._create_payment_vals_from_wizard(batch_result)
        res.update({
            'vacation_id': self.hr_vacation_id.id,
        })
        return res

    def _create_payment_vals_from_batch(self, batch_result):
        res = super()._create_payment_vals_from_batch(batch_result)
        res.update({
            'vacation_id': self.hr_vacation_id.id,
        })
        return res