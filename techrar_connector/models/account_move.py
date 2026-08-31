from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    techrar_order_id = fields.Char(string='Techrar Order ID', copy=False, index=True)
    techrar_subscription_id = fields.Char(string='Techrar Subscription ID', copy=False)
    techrar_subscription_status = fields.Char(string='Techrar Subscription Status', copy=False)
    techrar_subscription_days = fields.Integer(string='Techrar Subscription Days', copy=False)
    techrar_paused_days = fields.Integer(string='Techrar Paused Days', copy=False)
    techrar_payment_provider = fields.Char(string='Techrar Payment Provider', copy=False)
    techrar_payment_method = fields.Char(string='Techrar Payment Method', copy=False)
    techrar_customer_id = fields.Char(string='Techrar Customer ID', copy=False, index=True)
    techrar_customer_name = fields.Char(string='Techrar Customer Name', copy=False, index=True)
    techrar_customer_mobile = fields.Char(string='Techrar Customer Mobile', copy=False, index=True)
    techrar_customer_email = fields.Char(string='Techrar Customer Email', copy=False, index=True)
