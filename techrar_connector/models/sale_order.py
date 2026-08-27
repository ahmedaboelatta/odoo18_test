from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    techrar_order_id = fields.Char(string='Techrar Order ID', index=True)
    techrar_subscription_id = fields.Char(string='Techrar Subscription ID')
    techrar_branch_id = fields.Many2one(
        'techrar.branch',
        string='Techrar Branch',
        help='Branch associated with the Techrar order.',
    )
    techrar_delivery_type = fields.Selection(
        [('pickup', 'Branch Pickup'), ('delivery', 'Home Delivery')],
        string='Techrar Delivery Type',
    )
    techrar_delivery_address = fields.Text(string='Techrar Delivery Destination')
    techrar_import_status = fields.Selection([
        ('needs_mapping', 'Needs Mapping'), ('imported', 'Imported'),
        ('processed', 'Processed'), ('invoiced', 'Invoiced'), ('failed', 'Failed')
    ], string='Techrar Status', copy=False, index=True)
    techrar_subscription_name = fields.Char(copy=False)
    techrar_voucher_code = fields.Char(copy=False)
    techrar_start_date = fields.Date(copy=False)
    techrar_end_date = fields.Date(copy=False)
    techrar_delivery_fee = fields.Monetary(copy=False)
    techrar_wallet_discount = fields.Monetary(copy=False)
    techrar_total_discount = fields.Monetary(copy=False)
