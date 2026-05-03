from odoo import models,fields,api


class AccountPayment(models.Model):
    _inherit = 'account.payment'


    vacation_id = fields.Many2one('employee.vacation.settlement')

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        res = super()._prepare_move_line_default_vals(write_off_line_vals, force_balance)
        if self.vacation_id:
            print('resAhmed', res)
            for rec in res:
                rec.update({
                    'analytic_distribution': {
                        self.vacation_id.analytic_account_id.id: 100} if self.vacation_id.analytic_account_id else False,
                })
        return res