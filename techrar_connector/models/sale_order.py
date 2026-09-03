from datetime import datetime, time, timedelta

import pytz

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

    @api.model
    def get_techrar_dashboard_data(self):
        """Return operational KPIs without exposing configuration secrets."""
        today = fields.Date.context_today(self)
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        start_local = user_tz.localize(datetime.combine(today, time.min))
        start_utc = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = start_utc + timedelta(days=1)
        start_value = fields.Datetime.to_string(start_utc)
        end_value = fields.Datetime.to_string(end_utc)
        company_ids = self.env.companies.ids
        today_domain = [
            ('techrar_order_id', '!=', False),
            ('company_id', 'in', company_ids),
            ('date_order', '>=', start_value),
            ('date_order', '<', end_value),
        ]
        orders = self.search(today_domain)
        invoices = orders.invoice_ids.filtered(
            lambda invoice: invoice.move_type == 'out_invoice'
            and invoice.state != 'cancel'
        )
        payment_counts = {
            key: len(orders.filtered(lambda order: order.techrar_payment_state == key))
            for key in ('paid', 'not_paid', 'partial', 'in_payment', 'no_invoice', 'reversed')
        }
        provider_counts = {}
        for order in orders:
            provider = order.techrar_payment_provider or 'Unknown / Pending Details'
            provider_counts[provider] = provider_counts.get(provider, 0) + 1

        queue_model = self.env['techrar.webhook.event'].sudo()
        queue_base = [('config_id.company_id', 'in', company_ids)]
        pending_domain = queue_base + [('state', 'in', ('pending', 'processing'))]
        pending_events = queue_model.search(pending_domain, order='create_date', limit=1)
        queue_counts = {
            state: queue_model.search_count(queue_base + [('state', '=', state)])
            for state in ('pending', 'processing', 'failed')
        }

        log_model = self.env['techrar.sync.log'].sudo()
        log_domain = [
            ('create_date', '>=', start_value),
            ('create_date', '<', end_value),
        ]
        source_counts = {
            source: log_model.search_count(log_domain + [('run_source', '=', source)])
            for source in ('webhook', 'cron', 'manual')
        }
        configs = self.env['techrar.config'].sudo().search([
            ('company_id', 'in', company_ids),
        ])
        webhook_dates = [
            value for value in configs.mapped('webhook_last_received_at') if value
        ]
        sync_dates = [
            value for value in configs.mapped('last_successful_sync') if value
        ]
        last_webhook = max(webhook_dates, default=False)
        last_sync = max(sync_dates, default=False)
        currency = self.env.company.currency_id
        return {
            'date': fields.Date.to_string(today),
            'date_domain': today_domain,
            'currency': currency.name,
            'orders': {
                'total': len(orders),
                'invoiced': len(orders.filtered(lambda order: order.invoice_ids)),
                'sales_total': sum(orders.mapped('amount_total')),
                'invoice_total': sum(invoices.mapped('amount_total')),
                'paid_amount': sum(
                    invoice.amount_total - invoice.amount_residual
                    for invoice in invoices
                ),
                'residual_amount': sum(invoices.mapped('amount_residual')),
            },
            'payments': payment_counts,
            'providers': [
                {'name': name, 'count': count}
                for name, count in sorted(
                    provider_counts.items(), key=lambda item: item[1], reverse=True,
                )
            ],
            'queue': {
                **queue_counts,
                'oldest_pending': (
                    fields.Datetime.to_string(pending_events.create_date)
                    if pending_events else False
                ),
            },
            'sources': source_counts,
            'last_webhook': (
                fields.Datetime.to_string(last_webhook) if last_webhook else False
            ),
            'last_sync': fields.Datetime.to_string(last_sync) if last_sync else False,
        }
