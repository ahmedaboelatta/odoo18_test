from odoo import api, fields, models


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
    techrar_subscription_status = fields.Char(copy=False)
    techrar_subscription_days = fields.Integer(copy=False)
    techrar_paused_days = fields.Integer(copy=False)
    techrar_voucher_code = fields.Char(copy=False)
    techrar_start_date = fields.Date(copy=False)
    techrar_end_date = fields.Date(copy=False)
    techrar_delivery_fee = fields.Monetary(copy=False)
    techrar_wallet_discount = fields.Monetary(copy=False)
    techrar_total_discount = fields.Monetary(copy=False)
    techrar_payment_provider = fields.Char(string='Techrar Payment Provider', copy=False)
    techrar_payment_method = fields.Char(string='Techrar Payment Method', copy=False)
    techrar_customer_id = fields.Char(string='Techrar Customer ID', copy=False, index=True)
    techrar_customer_name = fields.Char(string='Techrar Customer Name', copy=False, index=True)
    techrar_customer_mobile = fields.Char(string='Techrar Customer Mobile', copy=False, index=True)
    techrar_customer_email = fields.Char(string='Techrar Customer Email', copy=False, index=True)
    techrar_payment_state = fields.Selection([
        ('no_invoice', 'No Invoice'),
        ('not_paid', 'Not Paid'),
        ('partial', 'Partially Paid'),
        ('in_payment', 'In Payment'),
        ('paid', 'Paid'),
        ('reversed', 'Reversed'),
    ], string='Payment Status', compute='_compute_techrar_payment_state', store=True,
       index=True)

    @api.depends('invoice_ids.state', 'invoice_ids.payment_state')
    def _compute_techrar_payment_state(self):
        for order in self:
            invoices = order.invoice_ids.filtered(
                lambda invoice: (
                    invoice.move_type == 'out_invoice'
                    and invoice.state != 'cancel'
                )
            )
            if not invoices:
                order.techrar_payment_state = 'no_invoice'
                continue
            states = set(invoices.mapped('payment_state'))
            if states == {'paid'}:
                payment_state = 'paid'
            elif states == {'reversed'}:
                payment_state = 'reversed'
            elif 'partial' in states or ('paid' in states and len(states) > 1):
                payment_state = 'partial'
            elif 'in_payment' in states:
                payment_state = 'in_payment'
            else:
                payment_state = 'not_paid'
            order.techrar_payment_state = payment_state
