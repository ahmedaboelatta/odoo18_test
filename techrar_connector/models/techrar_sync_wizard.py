import requests
import json
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class TechrarSyncWizard(models.TransientModel):
    _name = 'techrar.sync.wizard'
    _description = 'Techrar Orders Sync Wizard'

    from_date = fields.Date(string='From Date', required=True, default=fields.Date.today)
    to_date = fields.Date(string='To Date', required=True, default=fields.Date.today)

    def action_sync_orders(self):
        self.ensure_one()
        if self.from_date > self.to_date:
            raise UserError('From Date must be earlier than To Date.')

        api_base_url = self.env['ir.config_parameter'].sudo().get_param('techrar.api_base_url', default='https://api.techrar.com')
        token = self.env['ir.config_parameter'].sudo().get_param('techrar.api_token')
        app_id = self.env['ir.config_parameter'].sudo().get_param('techrar.app_id', default='3')

        if not token:
            raise UserError('Techrar API Token is not configured. Please configure it in Settings.')

        headers = {
            'Authorization': f'Bearer {token}',
            'app-id': str(app_id),
            'Content-Type': 'application/json',
        }

        url = f"{api_base_url.rstrip('/')}/public-api/v1/orders/"
        params = {
            'from_date': self.from_date.strftime('%Y-%m-%d'),
            'to_date': self.to_date.strftime('%Y-%m-%d'),
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                raise UserError(f"Failed to fetch orders from Techrar API: {response.text}")

            orders_list = response.json()
            if not isinstance(orders_list, list):
                raise UserError('Unexpected response format from Techrar API: expected a JSON array.')

            created_count = 0
            skipped_count = 0
            processed_sub_products = {}

            for order_data in orders_list:
                techrar_id = str(order_data.get('id'))

                existing = self.env['sale.order'].search([('techrar_order_id', '=', techrar_id)], limit=1)
                if existing:
                    skipped_count += 1
                    continue

                partner = self._get_or_create_partner(order_data.get('customer_profile', {}))
                order_lines, discount_lines = self._build_order_lines(order_data, processed_sub_products)

                if not order_lines:
                    _logger.warning('No valid order lines found for Techrar order %s, skipping.', techrar_id)
                    skipped_count += 1
                    continue

                branch_data = order_data.get('branch', {})
                branch = self._get_or_create_branch(branch_data)

                vals = {
                    'partner_id': partner.id,
                    'techrar_order_id': techrar_id,
                    'techrar_subscription_id': str(order_data.get('subscription', {}).get('id', '')),
                    'order_line': order_lines + discount_lines,
                }
                if branch:
                    vals['techrar_branch_id'] = branch.id

                created_order = self.env['sale.order'].create(vals)

                self._process_sale_order(created_order, order_data)
                created_count += 1

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Completed',
                    'message': f'Orders created: {created_count}, Skipped (duplicates): {skipped_count}',
                    'type': 'success',
                    'sticky': False,
                }
            }

        except requests.exceptions.Timeout:
            _logger.error('Techrar API request timed out.')
            raise UserError('Techrar API request timed out. Please try again later.')
        except requests.exceptions.ConnectionError:
            _logger.error('Cannot connect to Techrar API.')
            raise UserError('Cannot connect to Techrar API. Please check your network connection.')
        except UserError:
            raise
        except Exception as e:
            _logger.exception('Unexpected error during Techrar sync.')
            raise UserError(f"Unexpected error during Techrar sync: {str(e)}")

    def _process_sale_order(self, order, order_data):
        order.action_confirm()

        invoice = order._create_invoices()
        if not invoice:
            _logger.warning('Could not create invoice for Techrar order %s.', order.techrar_order_id)
            return

        try:
            invoice.action_post()
        except Exception as e:
            _logger.warning('Could not post invoice for Techrar order %s: %s', order.techrar_order_id, str(e))
            return

        gateway_raw = (order_data.get('provider') or order_data.get('payment_gateway') or '').lower()
        method_raw = (order_data.get('payment_method') or '').lower()

        journal = self._get_payment_journal(gateway_raw, method_raw)
        if not journal:
            _logger.warning('No matching payment journal found for provider/gateway "%s" / method "%s" on Techrar order %s.', order_data.get('provider') or order_data.get('payment_gateway'), order_data.get('payment_method'), order.techrar_order_id)
            return

        paid_amount = self._get_paid_amount(order_data, invoice)
        if not paid_amount:
            _logger.warning('No paid amount found for Techrar order %s, skipping payment registration.', order.techrar_order_id)
            return

        try:
            payment_register = self.env['account.payment.register'].with_context(
                active_model='account.move',
                active_ids=invoice.ids,
            ).create({
                'journal_id': journal.id,
                'payment_date': fields.Date.context_today(self),
                'amount': paid_amount,
            })
            payment_register.action_create_payments()
        except Exception as e:
            _logger.warning('Failed to register payment for Techrar order %s: %s', order.techrar_order_id, str(e))

    def _get_payment_journal(self, payment_gateway, payment_method):
        journal_name = 'Bank'

        if 'tabby' in payment_gateway:
            journal_name = 'Tabby Journal'
        elif 'tamara' in payment_gateway:
            journal_name = 'Tamara Journal'
        elif 'myfatoorah' in payment_gateway or 'ماي فاتورة' in payment_gateway:
            if 'apple' in payment_method:
                journal_name = 'Apple Pay Journal'
            elif 'mada' in payment_method:
                journal_name = 'Mada Journal'
            elif 'visa' in payment_method or 'master' in payment_method:
                journal_name = 'Visa/Master Journal'
            else:
                journal_name = 'MyFatoorah General Journal'
        elif 'mada' in payment_gateway or 'mada' in payment_method:
            journal_name = 'Mada Journal'

        return self.env['account.journal'].search([('name', 'ilike', journal_name), ('type', '=', 'bank')], limit=1)

    def _get_paid_amount(self, order_data, invoice):
        if order_data.get('total_amount'):
            return float(order_data.get('total_amount'))
        return float(invoice.amount_total)

    def _get_or_create_partner(self, profile):
        mobile = profile.get('mobile_number')
        if not mobile:
            raise UserError('Customer mobile number is missing in Techrar order data.')

        partner = self.env['res.partner'].search([('phone', '=', mobile)], limit=1)
        if partner:
            return partner

        return self.env['res.partner'].create({
            'name': profile.get('name') or f"Techrar Customer {mobile}",
            'phone': mobile,
            'email': profile.get('email'),
        })

    def _get_or_create_branch(self, branch_data):
        if not branch_data:
            return False

        branch_name_ar = branch_data.get('branch_name_ar')
        techrar_branch_id = str(branch_data.get('id', ''))

        if not branch_name_ar and not techrar_branch_id:
            return False

        branch = False
        if techrar_branch_id:
            branch = self.env['techrar.branch'].search([('techrar_branch_id', '=', techrar_branch_id)], limit=1)
        if not branch and branch_name_ar:
            branch = self.env['techrar.branch'].search([('name', '=', branch_name_ar)], limit=1)
        if not branch:
            branch = self.env['techrar.branch'].create({
                'name': branch_name_ar or branch_data.get('name', 'Unnamed Branch'),
                'techrar_branch_id': techrar_branch_id,
            })
        return branch

    def _build_order_lines(self, order_data, processed_sub_products=None):
        if processed_sub_products is None:
            processed_sub_products = {}

        sub_data = order_data.get('subscription', {})
        sub_id = str(sub_data.get('id', ''))
        sub_name = sub_data.get('name_ar', 'Unknown Subscription')
        num_of_days = sub_data.get('num_of_days') or 1
        cart_amount = order_data.get('cart_amount', 0.0)

        price_unit = cart_amount / num_of_days if num_of_days > 0 else cart_amount

        if sub_id in processed_sub_products:
            product_template = processed_sub_products[sub_id]
        else:
            product_template = self.env['product.template'].search([('techrar_subs_id', '=', str(sub_id))], limit=1)

            if not product_template:
                product_template = self.env['product.template'].create({
                    'name': sub_name,
                    'techrar_subs_id': str(sub_id),
                    'type': 'service',
                    'sale_ok': True,
                    'purchase_ok': False,
                    'invoice_policy': 'order',
                    'is_techrar_subscription': True,
                })
                self.env['product.template'].flush_model(['techrar_subs_id'])

            processed_sub_products[sub_id] = product_template

        product = product_template.product_variant_id

        order_lines = [(0, 0, {
            'product_id': product.id,
            'name': f"Subscription: {sub_name} (ID: {sub_id}) - Duration: {num_of_days} Days",
            'product_uom_qty': num_of_days,
            'price_unit': price_unit,
        })]

        discount_lines = []
        discount_amount = order_data.get('cart_amount_voucher_discounts', 0.0)
        if discount_amount and discount_amount > 0:
            discount_product = self.env['product.product'].search([('default_code', '=', 'DISC_TECHRAR')], limit=1)
            if not discount_product:
                discount_product = self.env['product.template'].create({
                    'name': 'Techrar Platform Discount',
                    'default_code': 'DISC_TECHRAR',
                    'type': 'service',
                    'sale_ok': True,
                    'purchase_ok': False,
                }).product_variant_id
            discount_lines.append((0, 0, {
                'product_id': discount_product.id,
                'name': f"Discount Code: {order_data.get('voucher_code', 'N/A')}",
                'product_uom_qty': 1.0,
                'price_unit': -abs(float(discount_amount)),
            }))

        return order_lines, discount_lines

    @api.model
    def _cron_sync_techrar_orders(self):
        today = fields.Date.today()
        wizard = self.create({
            'from_date': today,
            'to_date': today,
        })
        return wizard.action_sync_orders()
