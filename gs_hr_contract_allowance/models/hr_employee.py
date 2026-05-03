from odoo import fields, models, api


# class HREmployee(models.Model):
#    _inherit = 'hr.employee'
#
#    contract_allowances_ids = fields.One2many('hr.employee.allowance', 'employee_id',compute='get_contract_salary_info',readonly=True)
#    wage = fields.Float('Basic Salary', help="Employee's monthly gross wage.",compute='get_contract_salary_info')
#    trans_allowance_val = fields.Float(string="Transportation Amount",readonly=True,store=True)
#    house_allowance_val = fields.Float(string="House Amount",readonly=True,store=True)
#    other_allowance_val = fields.Float(string="Other Amount",readonly=True,store=True)
#
#    def get_contract_salary_info(self):
#         print('enter...')
#         contract = self.env['hr.contract'].search([('employee_id', '=', self.id), ('state', '=', 'open')], limit=1)
#         self.wage = contract.wage
#         self.house_allowance_val = contract.house_allowance_val
#         self.other_allowance_val = contract.other_allowance_val
#         self.trans_allowance_val = contract.trans_allowance_val
#         if contract.contract_allowances:
#             for rec in contract.contract_allowances:
#                allowance_name = rec.allowance_id.id
#                amount = rec.amount
#                print('allowance_name = ', allowance_name)
#                print('amount = ', amount)
#                self.contract_allowances_ids.create(
#                    {'employee_id': self.id, 'allowance_id': allowance_name, 'amount': amount, 'is_paid': True})
#         else:
#             print('else .....')
#             self.contract_allowances_ids = (0, 0, {
#                             'amount': 0.0
#                         })

# class HREmployeeAllowances(models.Model):
#    _name= 'hr.employee.allowance'
#    _description = 'Allowances'
#    employee_id  = fields.Many2one(
#     comodel_name='hr.employee',
#     string='Allowances line',
#     required=False)
#
#    allowance_id = fields.Many2one('hr.allowance', 'Allowance')
#    currency_id = fields.Many2one(string="Currency", readonly=True,default=lambda self:self.env.company.currency_id)
#    amount = fields.Float(string="Amount")
#    is_paid = fields.Boolean(string="Paid", default=True)






