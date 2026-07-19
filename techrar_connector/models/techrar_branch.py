from odoo import fields, models


class TechrarBranch(models.Model):
    _name = 'techrar.branch'
    _description = 'Techrar Branch'

    name = fields.Char(string='Branch Name (AR)', required=True)
    branch_name_en = fields.Char(string='Branch Name (EN)')
    techrar_branch_id = fields.Char(string='Techrar Branch ID', index=True)
    city_name_en = fields.Char(string='City Name (EN)')
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        help='Optional mapping to an Odoo warehouse.',
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        help='Optional mapping to an Odoo analytic account.',
    )
    active = fields.Boolean(string='Active', default=True)
