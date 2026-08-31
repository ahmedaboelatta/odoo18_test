import requests
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class TechrarSyncWizard(models.TransientModel):
    _name = 'techrar.sync.wizard'
    _description = 'Techrar Orders Sync Wizard'

    MAX_SYNC_RANGE_DAYS = 1

    from_date = fields.Date(string='From Date', required=True, default=fields.Date.today)
    to_date = fields.Date(string='To Date', required=True, default=fields.Date.today)
    config_id = fields.Many2one(
        'techrar.config', string='Configuration', required=True,
        default=lambda self: self.env['techrar.config'].with_context(active_test=False).search([], limit=1),
    )
    run_source = fields.Selection([('manual', 'Manual'), ('cron', 'Scheduled')], default='manual', required=True)

    def action_sync_orders(self):
        self.ensure_one()
        if self.from_date > self.to_date:
            raise UserError('From Date must be earlier than To Date.')
        range_days = (self.to_date - self.from_date).days + 1
        if range_days > self.MAX_SYNC_RANGE_DAYS:
            raise UserError(
                'For server safety, synchronize one day at a time. '
                'Select the same date in From Date and To Date.'
            )

        config = self.config_id
        if not config:
            raise UserError('No active Techrar configuration was found.')
        api_base_url = config.techrar_api_url
        token = config.techrar_api_token
        app_id = config.techrar_app_id

        if not token:
            raise UserError('Techrar API Token is not configured. Please configure it in Settings.')
        setup_issues = config._get_setup_issues()
        if setup_issues:
            raise UserError('Complete Techrar Configuration:\n- ' + '\n- '.join(setup_issues))

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
            updated_count = 0
            skipped_count = 0
            deferred_count = 0
            work_count = 0
            api_order_ids = [
                str(order.get('id')) for order in orders_list if order.get('id')
            ]
            existing_orders = self.env['sale.order'].search([
                ('techrar_order_id', 'in', api_order_ids),
            ]) if api_order_ids else self.env['sale.order']
            existing_by_techrar_id = {
                order.techrar_order_id: order for order in existing_orders
            }
            for order_data in orders_list:
                techrar_id = str(order_data.get('id') or '')
                if not techrar_id:
                    skipped_count += 1
                    self._create_log('', 'failed', 'The API order has no ID.')
                    continue
                existing = existing_by_techrar_id.get(
                    techrar_id, self.env['sale.order']
                )
                if self._is_fully_imported(existing):
                    skipped_count += 1
                    continue
                if work_count >= config.sync_batch_size:
                    deferred_count += 1
                    continue
                work_count += 1
                try:
                    with self.env.cr.savepoint():
                        result = self._import_one_order(
                            order_data,
                            config,
                            existing=existing,
                        )
                    if result == 'created':
                        created_count += 1
                    elif result == 'updated':
                        updated_count += 1
                    else:
                        skipped_count += 1
                except Exception as error:
                    skipped_count += 1
                    _logger.exception('Failed to import Techrar order %s.', techrar_id)
                    self._create_log(techrar_id, 'failed', str(error))

            config.last_successful_sync = fields.Datetime.now()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Completed',
                    'message': (
                        f'Orders created: {created_count}, Repaired: {updated_count}, '
                        f'Skipped: {skipped_count}, Remaining for this day: {deferred_count}. '
                        f'Run the same date again to continue.'
                    ),
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

    def _import_one_order(self, order_data, config, existing=None):
        techrar_id = str(order_data.get('id'))
        if existing is None:
            existing = self.env['sale.order'].search([
                ('techrar_order_id', '=', techrar_id),
            ], limit=1)
        if self._is_fully_imported(existing):
            return 'skipped'

        partner = config.invoice_partner_id
        branch_data = order_data.get('branch') or {}
        branch = self._get_or_create_branch(branch_data)
        order_lines = self._build_order_lines(order_data, config)
        vals = self._prepare_order_values(order_data, partner, branch)
        if existing:
            # Replace the label-only V3.0 lines with a financial line and a
            # descriptive note when the same API order is synchronized again.
            order_lines = [(5, 0, 0)] + order_lines
        vals.update({'order_line': order_lines, 'techrar_import_status': 'imported'})
        if existing:
            existing.write(vals)
            order = existing
        else:
            order = self.env['sale.order'].create(vals)
        self._create_log(techrar_id, 'imported', 'Order imported successfully.', order)
        self._process_sale_order(order, order_data, config)
        return 'updated' if existing else 'created'

    @staticmethod
    def _is_fully_imported(order):
        if not order:
            return False
        has_financial_line = any(
            not line.display_type and line.product_id for line in order.order_line
        )
        return bool(has_financial_line or order.invoice_ids)

    def _prepare_order_values(self, order_data, partner, branch):
        sub_data = order_data.get('subscription') or {}
        customer_profile = order_data.get('customer_profile') or {}
        branch_data = order_data.get('branch') or {}
        is_pickup = bool(order_data.get('is_pickup'))
        if is_pickup:
            branch_name = branch_data.get('branch_name_ar') or branch_data.get('branch_name_en') or 'Unknown Branch'
            city_name = branch_data.get('city_name_ar') or branch_data.get('city_name_en') or ''
            delivery_address = f"الاستلام من فرع: {branch_name} ({city_name})"
        else:
            delivery_address = (order_data.get('location') or {}).get('address') or 'No address provided'
        vals = {
            'company_id': self.config_id.company_id.id,
            'partner_id': partner.id,
            'techrar_customer_id': str(customer_profile.get('id') or ''),
            'techrar_customer_name': customer_profile.get('name'),
            'techrar_customer_mobile': customer_profile.get('mobile_number'),
            'techrar_customer_email': customer_profile.get('email'),
            'techrar_order_id': str(order_data.get('id')),
            'techrar_subscription_id': str(sub_data.get('id') or ''),
            'techrar_subscription_name': sub_data.get('name_ar') or sub_data.get('name_en'),
            'techrar_subscription_status': sub_data.get('status'),
            'techrar_subscription_days': int(sub_data.get('num_of_days') or 0),
            'techrar_paused_days': int(sub_data.get('paused_days') or 0),
            'techrar_delivery_type': 'pickup' if is_pickup else 'delivery',
            'techrar_delivery_address': delivery_address,
            'techrar_branch_id': branch.id if branch else False,
            'techrar_voucher_code': order_data.get('voucher_code'),
            'techrar_start_date': sub_data.get('start_date'),
            'techrar_end_date': sub_data.get('end_date'),
            'techrar_delivery_fee': self._as_float(order_data.get('delivery_fee')),
            'techrar_wallet_discount': self._as_float(order_data.get('wallet_discounts')),
            'techrar_total_discount': self._as_float(order_data.get('total_discounts')),
            'techrar_payment_provider': order_data.get('provider'),
            'techrar_payment_method': order_data.get('payment_method'),
        }
        created_at = order_data.get('created_at')
        if created_at:
            try:
                vals['date_order'] = fields.Datetime.to_datetime(created_at)
            except (TypeError, ValueError):
                _logger.warning('Invalid created_at value on Techrar order %s: %s', order_data.get('id'), created_at)
        return vals

    def _process_sale_order(self, order, order_data, config):
        if not config.auto_confirm_orders:
            return
        if order.state in ('draft', 'sent'):
            order.action_confirm()
        order.techrar_import_status = 'processed'
        self._create_log(order.techrar_order_id, 'processed', 'Order confirmed.', order)

        if not config.auto_create_invoices:
            return
        invoice = order._create_invoices()
        if not invoice:
            _logger.warning('Could not create invoice for Techrar order %s.', order.techrar_order_id)
            return
        invoice.write({
            'invoice_date': fields.Date.to_date(order.date_order),
            'ref': f'Techrar Order {order.techrar_order_id}',
            'techrar_order_id': order.techrar_order_id,
            'techrar_subscription_id': order.techrar_subscription_id,
            'techrar_subscription_status': order.techrar_subscription_status,
            'techrar_subscription_days': order.techrar_subscription_days,
            'techrar_paused_days': order.techrar_paused_days,
            'techrar_payment_provider': order.techrar_payment_provider,
            'techrar_payment_method': order.techrar_payment_method,
            'techrar_customer_id': order.techrar_customer_id,
            'techrar_customer_name': order.techrar_customer_name,
            'techrar_customer_mobile': order.techrar_customer_mobile,
            'techrar_customer_email': order.techrar_customer_email,
        })
        invoice.action_post()
        order.techrar_import_status = 'invoiced'
        self._create_log(order.techrar_order_id, 'invoiced', 'Invoice created and posted.', order)

        if not config.auto_register_payments:
            return
        gateway_raw = (order_data.get('provider') or order_data.get('payment_gateway') or '').lower()
        method_raw = (order_data.get('payment_method') or '').lower()
        journal = self._get_payment_journal(gateway_raw, method_raw, config)
        if not journal:
            _logger.warning(
                'No matching payment journal for Techrar order %s.', order.techrar_order_id
            )
            return
        paid_amount = self._get_order_amount(order_data)
        if paid_amount <= 0:
            return
        payment_register = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({
            'journal_id': journal.id,
            'payment_date': fields.Date.context_today(self),
            'amount': min(paid_amount, invoice.amount_residual),
            'communication': self._get_payment_memo(invoice, order.techrar_payment_method),
        })
        payment_register.action_create_payments()

    @staticmethod
    def _get_payment_memo(invoice, payment_method):
        invoice_number = invoice.name or invoice.ref or 'Techrar Invoice'
        return f'{invoice_number} - {payment_method}' if payment_method else invoice_number

    @staticmethod
    def _get_payment_journal(payment_gateway, payment_method, config):
        del payment_method  # Kept on the order for reporting; provider controls settlement.
        if payment_gateway == 'myfatoorah':
            return config.myfatoorah_journal_id
        if payment_gateway == 'tamara':
            return config.tamara_journal_id
        if payment_gateway == 'tabby':
            return config.tabby_journal_id or config.default_payment_journal_id
        return config.default_payment_journal_id

    def _get_or_create_branch(self, branch_data):
        if not branch_data:
            return False

        branch_name_ar = branch_data.get('branch_name_ar')
        branch_name_en = branch_data.get('branch_name_en')
        techrar_branch_id = str(branch_data.get('id', ''))
        city_name_en = branch_data.get('city_name_ar', branch_data.get('city_name_en', ''))

        if not branch_name_ar and not techrar_branch_id:
            return False

        branch = False
        if techrar_branch_id:
            branch = self.env['techrar.branch'].search([('techrar_branch_id', '=', techrar_branch_id)], limit=1)
        if not branch and branch_name_ar:
            branch = self.env['techrar.branch'].search([('name', '=', branch_name_ar)], limit=1)
        if not branch and branch_name_en and city_name_en:
            branch = self.env['techrar.branch'].search([
                ('branch_name_en', '=', branch_name_en),
                ('city_name_en', '=', city_name_en),
            ], limit=1)
        if not branch:
            branch = self.env['techrar.branch'].create({
                'name': branch_name_ar or branch_data.get('name', 'Unnamed Branch'),
                'branch_name_en': branch_name_en,
                'techrar_branch_id': techrar_branch_id,
                'city_name_en': city_name_en,
            })
        return branch

    def _build_order_lines(self, order_data, config):
        sub_data = order_data.get('subscription', {})
        sub_id = str(sub_data.get('id') or '')
        sub_name = sub_data.get('name_ar') or sub_data.get('name_en') or 'Techrar Subscription'
        duration = sub_data.get('num_of_days')
        label_parts = [sub_name]
        if sub_id:
            label_parts.append(f'Techrar Subscription ID: {sub_id}')
        if duration:
            label_parts.append(f'Duration: {duration} days')
        amount = self._get_order_amount(order_data)
        label_parts.append(f'Order amount: {amount:.2f}')
        description = ' | '.join(label_parts)
        return [(0, 0, {
            'product_id': config.general_product_id.id,
            'name': description,
            'product_uom_qty': 1.0,
            'price_unit': amount,
        }), (0, 0, {
            'display_type': 'line_note',
            'name': description,
        })]

    def _get_order_amount(self, order_data):
        total_amount = order_data.get('total_amount')
        if total_amount not in (None, ''):
            return self._as_float(total_amount)
        cart_amount = self._as_float(order_data.get('cart_amount'))
        delivery_fee = self._as_float(order_data.get('delivery_fee'))
        total_discounts = self._as_float(order_data.get('total_discounts'))
        return max(cart_amount + delivery_fee - total_discounts, 0.0)

    def _create_log(self, techrar_order_id, status, message, order=False):
        return self.env['techrar.sync.log'].create({
            'techrar_order_id': techrar_order_id,
            'sale_order_id': order.id if order else False,
            'status': status,
            'message': message,
            'run_source': self.run_source,
        })

    @staticmethod
    def _as_float(value):
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @api.model
    def _cron_sync_techrar_orders(self):
        config = self.env['techrar.config'].with_context(active_test=False).search([], limit=1)
        if not config:
            _logger.warning('Techrar scheduled sync skipped: no active configuration.')
            return False
        if config.sync_interval_minutes < 5:
            _logger.error(
                'Techrar scheduled sync disabled for safety: interval must be at least 5 minutes.'
            )
            return False
        today = fields.Date.today()
        wizard = self.create({
            'from_date': today,
            'to_date': today,
            'config_id': config.id,
            'run_source': 'cron',
        })
        return wizard.action_sync_orders()
