from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    techrar_order_id = fields.Char(string='Techrar Order ID', copy=False, index=True)
    techrar_subscription_id = fields.Char(string='Techrar Subscription ID', copy=False)
    techrar_payment_provider = fields.Char(string='Techrar Payment Provider', copy=False)
    techrar_payment_method = fields.Char(string='Techrar Payment Method', copy=False)
