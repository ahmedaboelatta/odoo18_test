from odoo import  models ,fields,api


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'


    def action_draft(self):
        res = super().action_draft()
        self.slip_ids.move_id.write({'state': 'draft'})
        self.slip_ids.move_id.unlink()
        self.slip_ids.write({'state': 'cancel'})
        self.slip_ids.write({'state': 'draft'})
        return res
