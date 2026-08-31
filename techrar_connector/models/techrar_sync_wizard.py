import requests
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class TechrarSyncWizard(models.TransientModel):
    _name = 'techrar.sync.wizard'
    _description = 'Techrar Orders Sync Wizard'

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

        config = self.config_id
        if not config:
            raise UserError('No active Techrar configuration was found.')
        api_base_url = config.techrar_api_url
        token = config.techrar_api_token
        app_id = config.techrar_app_id

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
            for order_data in orders_list:
                techrar_id = str(order_data.get('id') or '')
                if not techrar_id:
                    skipped_count += 1
                    self._create_log('', 'failed', 'The API order has no ID.')
                    continue
                try:
                    with self.env.cr.savepoint():
                        result = self._import_one_order(order_data, config)
                    if result == 'created':
                        created_count += 1
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

    def _import_one_order(self, order_data, config):
        techrar_id = str(order_data.get('id'))
        existing = self.env['sale.order'].search([('techrar_order_id', '=', techrar_id)], limit=1)
        if existing and existing.techrar_import_status != 'needs_mapping':
            self._create_log(techrar_id, 'skipped', 'Order already imported.', existing)
            return 'skipped'

        partner = self._get_or_create_partner(order_data.get('customer_profile') or {})
        branch_data = order_data.get('branch') or {}
        branch = self._get_or_create_branch(branch_data)
        order_lines = self._build_order_lines(order_data)
        vals = self._prepare_order_values(order_data, partner, branch)
        vals.update({'order_line': order_lines, 'techrar_import_status': 'imported'})
        if existing:
            existing.write(vals)
            order = existing
        else:
            order = self.env['sale.order'].create(vals)
        self._create_log(techrar_id, 'imported', 'Order imported successfully.', order)
        self._process_sale_order(order, order_data, config)
        return 'created'

    def _prepare_order_values(self, order_data, partner, branch):
        sub_data = order_data.get('subscription') or {}
        branch_data = order_data.get('branch') or {}
        is_pickup = bool(order_data.get('is_pickup'))
        if is_pickup:
            branch_name = branch_data.get('branch_name_ar') or branch_data.get('branch_name_en') or 'Unknown Branch'
            city_name = branch_data.get('city_name_ar') or branch_data.get('city_name_en') or ''
            delivery_address = f"الاستلام من فرع: {branch_name} ({city_name})"
        else:
            delivery_address = (order_data.get('location') or {}).get('address') or 'No address provided'
        vals = {
            'partner_id': partner.id,
            'techrar_order_id': str(order_data.get('id')),
            'techrar_subscription_id': str(sub_data.get('id') or ''),
            'techrar_subscription_name': sub_data.get('name_ar') or sub_data.get('name_en'),
            'techrar_delivery_type': 'pickup' if is_pickup else 'delivery',
            'techrar_delivery_address': delivery_address,
            'techrar_branch_id': branch.id if branch else False,
            'techrar_voucher_code': order_data.get('voucher_code'),
            'techrar_start_date': order_data.get('start_date'),
            'techrar_end_date': order_data.get('end_date'),
            'techrar_delivery_fee': self._as_float(order_data.get('delivery_fee')),
            'techrar_wallet_discount': self._as_float(order_data.get('wallet_discounts')),
            'techrar_total_discount': self._as_float(order_data.get('total_discounts')),
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
        order.action_confirm()
        order.techrar_import_status = 'processed'
        self._create_log(order.techrar_order_id, 'processed', 'Order confirmed.', order)

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

    def _build_order_lines(self, order_data):
        sub_data = order_data.get('subscription', {})
        sub_id = str(sub_data.get('id') or '')
        sub_name = sub_data.get('name_ar') or sub_data.get('name_en') or 'Techrar Subscription'
        duration = sub_data.get('num_of_days')
        label_parts = [sub_name]
        if sub_id:
            label_parts.append(f'Techrar Subscription ID: {sub_id}')
        if duration:
            label_parts.append(f'Duration: {duration} days')
        label_parts.append(f"Order amount: {self._as_float(order_data.get('total_amount')):.2f}")
        return [(0, 0, {
            'display_type': 'line_note',
            'name': ' | '.join(label_parts),
        })]

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
        today = fields.Date.today()
        wizard = self.create({
            'from_date': today,
            'to_date': today,
            'config_id': config.id,
            'run_source': 'cron',
        })
        return wizard.action_sync_orders()
