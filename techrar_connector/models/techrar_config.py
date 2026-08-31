from odoo import api, fields, models
from odoo.exceptions import UserError
import requests
import logging
import secrets

_logger = logging.getLogger(__name__)


class TechrarConfig(models.Model):
    _name = 'techrar.config'
    _description = 'Techrar Configuration'

    name = fields.Char(required=True, default='Techrar Main')
    techrar_api_url = fields.Char(string='API Base URL', required=True, default='https://api.techrar.com')
    techrar_api_token = fields.Char(string='API Token', required=True, password=True)
    techrar_app_id = fields.Char(string='App ID', default='3')
    general_product_id = fields.Many2one(
        'product.product',
        string='General Techrar Product',
        domain=[('sale_ok', '=', True)],
        ondelete='restrict',
        help='Existing Odoo product used for every Techrar financial line. The connector never creates products.',
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company
    )
    invoice_partner_id = fields.Many2one(
        'res.partner',
        string='Invoice Customer',
        ondelete='restrict',
        help=(
            'Accounting customer used on every Techrar quotation and invoice. '
            'The original Techrar customer details are kept as searchable reference fields.'
        ),
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ondelete='restrict',
        help=(
            'Optional analytic account applied at 100% to Techrar sales order lines, '
            'invoice lines, and payment journal items.'
        ),
    )
    myfatoorah_journal_id = fields.Many2one(
        'account.journal', string='MyFatoorah Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        ondelete='restrict',
    )
    tamara_journal_id = fields.Many2one(
        'account.journal', string='Tamara Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        ondelete='restrict',
    )
    tabby_journal_id = fields.Many2one(
        'account.journal', string='Tabby Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        ondelete='restrict',
        help='Optional while Tabby is disabled. Select it before enabling Tabby settlements.',
    )
    default_payment_journal_id = fields.Many2one(
        'account.journal', string='Default Payment Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        ondelete='restrict',
        help='Used only when Techrar returns an unknown payment provider.',
    )
    auto_confirm_orders = fields.Boolean(string='Automatically Confirm Orders', default=False)
    auto_create_invoices = fields.Boolean(string='Automatically Create Invoices', default=False)
    auto_register_payments = fields.Boolean(string='Automatically Register Payments', default=False)
    auto_sync_enabled = fields.Boolean(string='Enable Scheduled Sync', default=True)
    sync_interval_minutes = fields.Integer(
        string='Sync Every (Minutes)', default=10,
        help='Scheduled frequency. Batch size limits the work performed by each run.',
    )
    sync_lookback_days = fields.Integer(
        string='Sync Lookback (Days)', default=1,
        help='Re-fetch recent days on every run. Existing Techrar order IDs are safely skipped.',
    )
    sync_batch_size = fields.Integer(
        string='Orders per Run', default=100,
        help='Maximum new or repairable orders processed per run to protect the Odoo worker.',
    )
    last_successful_sync = fields.Datetime(readonly=True)
    last_connection_at = fields.Datetime(readonly=True)
    connection_status = fields.Selection([
        ('unknown', 'Not Checked'), ('connected', 'Connected'), ('failed', 'Failed')
    ], default='unknown', readonly=True)
    webhook_token = fields.Char(
        string='Webhook Security Token', copy=False,
        help='Secret value sent by Techrar in the X-Techrar-Odoo-Token header.',
    )
    webhook_public_base_url = fields.Char(
        string='Public Odoo URL',
        help='Public HTTPS address reachable by Techrar, for example https://odoo.example.com.',
    )
    webhook_url = fields.Char(string='Webhook URL', compute='_compute_webhook_url')
    webhook_last_received_at = fields.Datetime(string='Last Webhook Received', readonly=True)
    webhook_last_status = fields.Selection([
        ('success', 'Success'), ('failed', 'Failed'),
    ], readonly=True)
    webhook_last_error = fields.Text(readonly=True)

    _sql_constraints = [
        ('techrar_config_name_unique', 'unique(name)', 'The configuration name must be unique.'),
    ]

    @api.constrains(
        'general_product_id', 'auto_confirm_orders',
        'auto_create_invoices', 'auto_register_payments',
        'myfatoorah_journal_id', 'tamara_journal_id', 'tabby_journal_id',
        'default_payment_journal_id',
        'sync_interval_minutes', 'sync_lookback_days', 'sync_batch_size', 'company_id',
        'invoice_partner_id', 'analytic_account_id', 'auto_sync_enabled', 'webhook_token',
        'webhook_public_base_url'
    )
    def _check_setup(self):
        for config in self:
            if config.general_product_id and not config.general_product_id.sale_ok:
                raise UserError('The general Techrar product must be available for Sales.')
            if (
                config.auto_create_invoices
                and config.general_product_id
                and config.general_product_id.invoice_policy != 'order'
            ):
                raise UserError(
                    'The general Techrar product invoicing policy must be set to Ordered quantities.'
                )
            if config.auto_create_invoices and not config.auto_confirm_orders:
                raise UserError('Automatic invoicing requires automatic order confirmation.')
            if config.auto_register_payments and not config.auto_create_invoices:
                raise UserError('Automatic payment registration requires automatic invoicing.')
            if config.auto_create_invoices and not config.general_product_id:
                raise UserError('Select the General Techrar Product before enabling automatic invoicing.')
            if config.auto_register_payments and (
                not config.myfatoorah_journal_id or not config.tamara_journal_id
            ):
                raise UserError(
                    'Select both MyFatoorah and Tamara journals before enabling automatic payments.'
                )
            journals = (
                config.myfatoorah_journal_id
                | config.tamara_journal_id
                | config.tabby_journal_id
                | config.default_payment_journal_id
            )
            if any(journal.company_id != config.company_id for journal in journals):
                raise UserError('All payment journals must belong to the configuration company.')
            if (
                config.analytic_account_id.company_id
                and config.analytic_account_id.company_id != config.company_id
            ):
                raise UserError(
                    'The analytic account must be shared or belong to the configuration company.'
                )
            if config.auto_sync_enabled and config.sync_interval_minutes < 1:
                raise UserError('Scheduled sync interval must be at least one minute.')
            if config.auto_sync_enabled and config.sync_lookback_days != 1:
                raise UserError('Sync lookback must be one day for server safety.')
            if not 10 <= config.sync_batch_size <= 500:
                raise UserError('Orders per run must be between 10 and 500.')
            if config.webhook_token and len(config.webhook_token) < 24:
                raise UserError('Webhook Security Token must contain at least 24 characters.')
            if (
                config.webhook_public_base_url
                and not config.webhook_public_base_url.lower().startswith('https://')
            ):
                raise UserError('Public Odoo URL must use HTTPS.')

    @api.depends('webhook_public_base_url')
    def _compute_webhook_url(self):
        system_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for config in self:
            base_url = config.webhook_public_base_url or system_base_url
            config.webhook_url = (
                f"{base_url.rstrip('/')}/techrar/webhook/order-completed"
                if base_url else False
            )

    def action_generate_webhook_token(self):
        self.ensure_one()
        self.webhook_token = secrets.token_urlsafe(32)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records[:1]._apply_cron_settings()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'auto_sync_enabled', 'sync_interval_minutes'} & set(vals):
            self[:1]._apply_cron_settings()
        return result

    def _apply_cron_settings(self):
        config = self[:1]
        cron = self.env.ref('techrar_connector.ir_cron_techrar_sync_orders', raise_if_not_found=False)
        if config and cron:
            cron.sudo().write({
                'active': config.auto_sync_enabled,
                'interval_number': config.sync_interval_minutes,
                'interval_type': 'minutes',
            })

    def action_check_connection(self):
        self.ensure_one()
        if not self.techrar_api_url or not self.techrar_api_token:
            raise UserError('Please enter API Base URL and API Token before checking connection.')

        url = f"{self.techrar_api_url.rstrip('/')}/public-api/v1/orders/"
        headers = {
            'Authorization': f'Bearer {self.techrar_api_token}',
            'app-id': str(self.techrar_app_id or '3'),
            'Content-Type': 'application/json',
        }
        params = {
            'from_date': fields.Date.today().strftime('%Y-%m-%d'),
            'to_date': fields.Date.today().strftime('%Y-%m-%d'),
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                setup_issues = self._get_setup_issues()
                if setup_issues:
                    self.write({'last_connection_at': fields.Datetime.now(), 'connection_status': 'connected'})
                    return self._connection_notification(
                        'API Connected - Setup Incomplete',
                        '\n'.join(setup_issues),
                        'warning',
                    )
                self.write({'last_connection_at': fields.Datetime.now(), 'connection_status': 'connected'})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Connection Successful',
                        'message': 'API connection and general product configuration are valid.',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self.write({'last_connection_at': fields.Datetime.now(), 'connection_status': 'failed'})
                return self._connection_notification(
                    'Connection Failed', f'HTTP {response.status_code}: {response.text}', 'danger'
                )
        except requests.exceptions.Timeout:
            self.write({'last_connection_at': fields.Datetime.now(), 'connection_status': 'failed'})
            return self._connection_notification('Connection Failed', 'Connection timed out.', 'danger')
        except requests.exceptions.ConnectionError:
            self.write({'last_connection_at': fields.Datetime.now(), 'connection_status': 'failed'})
            return self._connection_notification(
                'Connection Failed', 'Cannot connect to Techrar API. Check the URL and network.', 'danger'
            )
        except UserError:
            raise
        except Exception as e:
            self.write({'last_connection_at': fields.Datetime.now(), 'connection_status': 'failed'})
            raise UserError(f"Connection error: {str(e)}")

    @staticmethod
    def _connection_notification(title, message, notification_type):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notification_type,
                'sticky': notification_type == 'danger',
            },
        }

    def _get_setup_issues(self):
        self.ensure_one()
        issues = []
        if not self.invoice_partner_id:
            issues.append('Select the Invoice Customer used for all Techrar invoices.')
        if not self.general_product_id:
            issues.append('Select the General Techrar Product.')
        if self.auto_sync_enabled and self.sync_interval_minutes < 1:
            issues.append('Set Scheduled Sync interval to at least one minute.')
        if self.auto_sync_enabled and self.sync_lookback_days != 1:
            issues.append('Set Sync Lookback to one day for server safety.')
        if self.auto_register_payments and not self.myfatoorah_journal_id:
            issues.append('Select the MyFatoorah payment journal.')
        if self.auto_register_payments and not self.tamara_journal_id:
            issues.append('Select the Tamara payment journal.')
        return issues
