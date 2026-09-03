import re

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
    run_source = fields.Selection([
        ('manual', 'Manual'), ('cron', 'Scheduled'), ('webhook', 'Webhook'),
    ], default='manual', required=True)

    @api.model
    def _context_today(self):
        return fields.Date.context_today(self)

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
                if response.status_code == 429:
                    reset_match = re.search(
                        r'Limit resets at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',
                        response.text or '',
                    )
                    config.api_rate_limited_until = (
                        fields.Datetime.to_datetime(reset_match.group(1))
                        if reset_match
                        else fields.Datetime.add(fields.Datetime.now(), hours=24)
                    )
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Techrar API Limit Reached',
                            'message': (
                                'Automatic API synchronization is paused until '
                                f'{config.api_rate_limited_until}. Webhooks will continue.'
                            ),
                            'type': 'warning',
                            'sticky': True,
                        },
                    }
                raise UserError(f"Failed to fetch orders from Techrar API: {response.text}")

            if config.api_rate_limited_until:
                config.api_rate_limited_until = False

            orders_list = response.json()
            if not isinstance(orders_list, list):
                raise UserError('Unexpected response format from Techrar API: expected a JSON array.')
            # Always process the newest subscriptions first when today's API
            # response contains more orders than the configured safe batch.
            orders_list.sort(
                key=lambda order: order.get('created_at') or '',
                reverse=True,
            )

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
                    try:
                        with self.env.cr.savepoint():
                            repaired = self._repair_existing_metadata(
                                existing, order_data, config,
                            )
                        if repaired:
                            updated_count += 1
                        else:
                            skipped_count += 1
                    except Exception as error:
                        skipped_count += 1
                        _logger.exception(
                            'Failed to repair Techrar order %s.', techrar_id,
                        )
                        self._create_log(techrar_id, 'failed', str(error), existing)
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
                    elif result == 'deferred':
                        deferred_count += 1
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
        # The scheduled sync and webhook queue may receive the same order at
        # exactly the same time.  Do not wait for the competing transaction:
        # Odoo uses REPEATABLE READ and waiting here can leave the loser with
        # an old snapshot and raise a serialization failure.  The loser simply
        # defers the order to its next run while the lock owner imports it.
        self.env.cr.execute(
            'SELECT pg_try_advisory_xact_lock(hashtext(%s))',
            [f'techrar-order:{config.id}:{techrar_id}'],
        )
        if not self.env.cr.fetchone()[0]:
            return 'deferred'

        # The persistent unique key keeps retries idempotent after the lock is
        # released and also protects installations upgraded from older builds.
        self.env.cr.execute(
            '''
                INSERT INTO techrar_import_key
                    (config_id, techrar_order_id, create_uid, write_uid, create_date, write_date)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (config_id, techrar_order_id) DO NOTHING
            ''',
            [config.id, techrar_id, self.env.uid, self.env.uid],
        )
        import_key = self.env['techrar.import.key'].search([
            ('config_id', '=', config.id),
            ('techrar_order_id', '=', techrar_id),
        ], limit=1)
        if import_key.outcome == 'wallet_ignored':
            return 'skipped'

        existing = self.env['sale.order'].search([
            ('techrar_order_id', '=', techrar_id),
        ], limit=1)
        if self._is_fully_imported(existing):
            self._repair_existing_metadata(existing, order_data, config)
            return 'skipped'

        # The accounting integration follows the actual cash received by the
        # merchant.  A wallet-only redemption has no new cash inflow and must
        # not create a sale order or invoice (matching the Zoho flow).
        if self._is_wallet_only_order(order_data):
            import_key.outcome = 'wallet_ignored'
            self._create_log(
                techrar_id,
                'skipped',
                'Wallet-only order ignored: no external cash was received.',
            )
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
        import_key.outcome = 'imported'
        return 'updated' if existing else 'created'

    def _process_webhook_payload(self, payload, config):
        is_test_event = (
            payload.get('event') == 'test'
            or payload.get('test') is not None
            or (isinstance(payload.get('data'), dict) and payload['data'].get('event') == 'test')
        )
        if is_test_event and not self._extract_webhook_order_id(payload):
            return 'test_received', ''
        setup_issues = config._get_setup_issues()
        if setup_issues:
            raise UserError('Complete Techrar Configuration: ' + '; '.join(setup_issues))
        order_data = self._extract_webhook_order(payload)
        techrar_order_id = self._extract_webhook_order_id(payload, order_data)
        if not techrar_order_id:
            raise UserError('Techrar webhook payload does not contain an order ID.')
        partial_order_data = order_data
        if not order_data or (
            not order_data.get('subscription')
            and order_data.get('type') != 'add_on'
        ):
            try:
                fetched_order = self._fetch_webhook_order(
                    techrar_order_id, config,
                )
            except (requests.exceptions.RequestException, UserError):
                if not (
                    partial_order_data
                    and self.env.context.get('techrar_allow_partial')
                ):
                    raise
                fetched_order = False
            if fetched_order:
                order_data = fetched_order
            elif partial_order_data and self.env.context.get('techrar_allow_partial'):
                order_data = self._enrich_webhook_order(
                    partial_order_data, techrar_order_id, config,
                    fetch_detail=False,
                )
            else:
                order_data = False
        elif order_data.get('type') == 'add_on':
            order_data = self._enrich_webhook_order(
                order_data, techrar_order_id, config,
            )
        if not order_data:
            raise UserError(f'Techrar order {techrar_order_id} could not be retrieved.')
        result = self._import_one_order(order_data, config)
        return result, techrar_order_id

    def _enrich_webhook_order(
        self, order_data, techrar_order_id, config, fetch_detail=True,
    ):
        """Add descriptive data without making webhook accounting fragile."""
        enriched = dict(order_data)
        headers = {
            'Authorization': f'Bearer {config.techrar_api_token}',
            'app-id': str(config.techrar_app_id or '3'),
            'Content-Type': 'application/json',
        }
        if fetch_detail:
            try:
                response = requests.get(
                    f"{config.techrar_api_url.rstrip('/')}/public-api/v1/orders/"
                    f'{techrar_order_id}/',
                    headers=headers,
                    timeout=10,
                )
                if response.status_code == 200 and isinstance(response.json(), dict):
                    detail = response.json()
                    detail.update(enriched)
                    enriched = detail
            except requests.exceptions.RequestException:
                _logger.info(
                    'Techrar order %s has no retrievable detail; using webhook data.',
                    techrar_order_id,
                )

        customer = dict(enriched.get('customer_profile') or {})
        customer_id = str(customer.get('id') or enriched.get('customer_id') or '')
        if customer_id and not any(
            customer.get(field) for field in ('name', 'mobile_number', 'email')
        ):
            previous = self.env['sale.order'].search([
                ('company_id', '=', config.company_id.id),
                ('techrar_customer_id', '=', customer_id),
                ('techrar_customer_name', '!=', False),
            ], order='date_order desc, id desc', limit=1)
            if previous:
                customer.update({
                    'id': customer_id,
                    'name': previous.techrar_customer_name,
                    'mobile_number': previous.techrar_customer_mobile,
                    'email': previous.techrar_customer_email,
                })
        enriched['customer_profile'] = customer
        return enriched

    @staticmethod
    def _extract_webhook_order(payload):
        for candidate in (
            payload.get('order'), payload.get('data'), payload.get('payload'), payload,
        ):
            if isinstance(candidate, dict) and candidate.get('id') and (
                candidate.get('subscription') or candidate.get('customer_profile')
            ):
                return candidate
            if isinstance(candidate, dict) and candidate.get('order_id'):
                order = dict(candidate)
                order['id'] = order['order_id']
                order['cart_amount'] = order.get('total_cart_amount', 0)
                order['wallet_discounts'] = order.get('redeem_discounts', 0)
                order['customer_profile'] = {
                    'id': order.get('customer_id'),
                }
                return order
        return False

    def _repair_existing_metadata(self, order, order_data, config):
        """Backfill metadata and payment after a partial webhook import."""
        if not order or not order_data:
            return False
        repaired = False
        branch = self._get_or_create_branch(order_data.get('branch') or {})
        prepared = self._prepare_order_values(
            order_data, config.invoice_partner_id, branch,
        )
        sale_fields = (
            'techrar_customer_id', 'techrar_customer_name',
            'techrar_customer_mobile', 'techrar_customer_email',
            'techrar_subscription_id', 'techrar_subscription_name',
            'techrar_subscription_status', 'techrar_subscription_days',
            'techrar_paused_days', 'techrar_branch_id',
            'techrar_delivery_address', 'techrar_voucher_code',
            'techrar_start_date', 'techrar_end_date',
            'techrar_payment_provider', 'techrar_payment_method',
        )
        updates = {
            field: prepared[field]
            for field in sale_fields
            if prepared.get(field) and not order[field]
        }
        if updates:
            order.write(updates)
            repaired = True
            invoice_fields = set(order.invoice_ids._fields)
            invoice_updates = {
                field: value for field, value in updates.items()
                if field in invoice_fields
            }
            if invoice_updates:
                order.invoice_ids.write(invoice_updates)

        # An immediate webhook may contain the financial amount but not the
        # payment provider.  In that case the invoice is correctly posted but
        # payment registration is deferred until the scheduled API response
        # supplies the provider and its configured journal.
        if config.auto_register_payments:
            gateway_raw = (
                order_data.get('provider')
                or order_data.get('payment_gateway')
                or ''
            ).lower()
            method_raw = (order_data.get('payment_method') or '').lower()
            journal = self._get_payment_journal(
                gateway_raw, method_raw, config,
            )
            amount_left = self._get_external_paid_amount(order_data)
            invoices = order.invoice_ids.filtered(
                lambda invoice: (
                    invoice.state == 'posted'
                    and invoice.move_type == 'out_invoice'
                    and invoice.amount_residual > 0
                )
            ).sorted('id')
            if journal and amount_left > 0 and invoices:
                analytic_distribution = self._get_analytic_distribution(config)
                for invoice in invoices:
                    payment_amount = min(amount_left, invoice.amount_residual)
                    if payment_amount <= 0:
                        break
                    self._register_invoice_payment(
                        invoice,
                        journal,
                        payment_amount,
                        order_data.get('payment_method'),
                        analytic_distribution,
                    )
                    amount_left -= payment_amount
                    repaired = True
                self._create_log(
                    order.techrar_order_id,
                    'processed',
                    'Missing invoice payment registered from refreshed API data.',
                    order,
                )
        return repaired

    @staticmethod
    def _extract_webhook_order_id(payload, order_data=False):
        if order_data:
            return str(order_data.get('id') or '')
        candidates = []
        for key in ('order', 'data', 'payload'):
            if isinstance(payload.get(key), dict):
                candidates.append(payload[key])
        candidates.append(payload)
        for index, candidate in enumerate(candidates):
            value = candidate.get('order_id') or candidate.get('orderId')
            if not value and index < len(candidates) - 1:
                value = candidate.get('id')
            if value:
                return str(value)
        if payload.get('id') and any(
            key in payload for key in ('subscription', 'customer_profile', 'cart', 'invoice')
        ):
            return str(payload['id'])
        return ''

    def _fetch_webhook_order(self, techrar_order_id, config):
        headers = {
            'Authorization': f'Bearer {config.techrar_api_token}',
            'app-id': str(config.techrar_app_id or '3'),
            'Content-Type': 'application/json',
        }
        base_url = config.techrar_api_url.rstrip('/')
        detail_response = requests.get(
            f'{base_url}/public-api/v1/orders/{techrar_order_id}/',
            headers=headers,
            timeout=20,
        )
        if detail_response.status_code == 200:
            detail = detail_response.json()
            if isinstance(detail, dict):
                return detail

        today = fields.Date.context_today(self).strftime('%Y-%m-%d')
        list_response = requests.get(
            f'{base_url}/public-api/v1/orders/',
            headers=headers,
            params={'from_date': today, 'to_date': today},
            timeout=30,
        )
        if list_response.status_code != 200:
            raise UserError(
                f'Could not retrieve Techrar order {techrar_order_id}: '
                f'HTTP {list_response.status_code}.'
            )
        orders = list_response.json()
        return next((
            order for order in orders
            if str(order.get('id') or '') == str(techrar_order_id)
        ), False) if isinstance(orders, list) else False

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
        analytic_distribution = self._get_analytic_distribution(config)
        if analytic_distribution:
            invoice.invoice_line_ids.filtered(
                lambda line: not line.display_type
            ).write({'analytic_distribution': analytic_distribution})
        invoice.action_post()
        order.techrar_import_status = 'invoiced'
        self._create_log(order.techrar_order_id, 'invoiced', 'Invoice created and posted.', order)

        if not config.auto_register_payments:
            return
        external_paid_amount = self._get_external_paid_amount(order_data)
        if external_paid_amount <= 0 or invoice.amount_residual <= 0:
            return
        gateway_raw = (order_data.get('provider') or order_data.get('payment_gateway') or '').lower()
        method_raw = (order_data.get('payment_method') or '').lower()
        journal = self._get_payment_journal(gateway_raw, method_raw, config)
        if not journal:
            _logger.warning(
                'No matching payment journal for Techrar order %s.', order.techrar_order_id
            )
            return
        self._register_invoice_payment(
            invoice,
            journal,
            external_paid_amount,
            order.techrar_payment_method,
            analytic_distribution,
        )

    def _register_invoice_payment(
        self, invoice, journal, amount, payment_label, analytic_distribution,
    ):
        amount = min(amount, invoice.amount_residual)
        if amount <= 0:
            return self.env['account.payment']
        payment_register = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({
            'journal_id': journal.id,
            'payment_date': fields.Date.context_today(self),
            'amount': amount,
            'communication': self._get_payment_memo(invoice, payment_label),
        })
        payments_before = invoice._get_reconciled_payments()
        payment_register.action_create_payments()
        new_payments = invoice._get_reconciled_payments() - payments_before
        if analytic_distribution:
            new_payments.move_id.line_ids.write({
                'analytic_distribution': analytic_distribution,
            })
        return new_payments

    @staticmethod
    def _get_analytic_distribution(config):
        if not config.analytic_account_id:
            return False
        return {str(config.analytic_account_id.id): 100.0}

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
        sub_name = sub_data.get('name_ar') or sub_data.get('name_en')
        if not sub_name:
            sub_name = (
                'Techrar Add-on Order'
                if order_data.get('type') == 'add_on'
                else 'Techrar Subscription'
            )
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
            'analytic_distribution': self._get_analytic_distribution(config),
        }), (0, 0, {
            'display_type': 'line_note',
            'name': description,
        })]

    def _get_order_amount(self, order_data):
        total_amount = order_data.get('total_amount')
        if total_amount not in (None, ''):
            # This connector intentionally mirrors the cash received by the
            # merchant.  Techrar total_amount is the external cash portion
            # after wallet redemption, so do not add wallet points back.
            return max(self._as_float(total_amount), 0.0)
        cart_amount = self._as_float(order_data.get('cart_amount'))
        delivery_fee = self._as_float(order_data.get('delivery_fee'))
        total_discounts = self._as_float(order_data.get('total_discounts'))
        return max(cart_amount + delivery_fee - total_discounts, 0.0)

    def _get_wallet_amount(self, order_data):
        return max(self._as_float(
            order_data.get('wallet_discounts', order_data.get('redeem_discounts'))
        ), 0.0)

    def _get_external_paid_amount(self, order_data):
        total_amount = order_data.get('total_amount')
        if total_amount not in (None, ''):
            return max(self._as_float(total_amount), 0.0)
        return self._get_order_amount(order_data)

    def _is_wallet_only_order(self, order_data):
        return (
            self._get_wallet_amount(order_data) > 0
            and self._get_external_paid_amount(order_data) <= 0
        )

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
        now = fields.Datetime.now()
        if config.api_rate_limited_until and config.api_rate_limited_until > now:
            _logger.info(
                'Techrar scheduled sync paused until %s after API rate limiting.',
                config.api_rate_limited_until,
            )
            return False
        # Webhooks handle new orders immediately. Keep polling as an hourly
        # reconciliation safety net without exhausting the daily API allowance.
        if (
            config.last_successful_sync
            and config.last_successful_sync > fields.Datetime.subtract(now, minutes=55)
        ):
            return False
        today = fields.Date.today()
        result = False
        # Run each calendar day separately so the one-day safety limit remains
        # intact while still covering orders created just before midnight.
        # A lookback of 1 means today plus yesterday.
        for offset in range(config.sync_lookback_days + 1):
            sync_date = fields.Date.subtract(today, days=offset)
            wizard = self.create({
                'from_date': sync_date,
                'to_date': sync_date,
                'config_id': config.id,
                'run_source': 'cron',
            })
            result = wizard.action_sync_orders()
            if config.api_rate_limited_until:
                break
        return result
