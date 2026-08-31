from odoo import api, fields, models
from odoo.exceptions import UserError
import requests
import logging

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
    sync_interval_minutes = fields.Integer(string='Sync Every (Minutes)', default=10)
    sync_lookback_days = fields.Integer(
        string='Sync Lookback (Days)', default=1,
        help='Re-fetch recent days on every run. Existing Techrar order IDs are safely skipped.',
    )
    last_successful_sync = fields.Datetime(readonly=True)
    last_connection_at = fields.Datetime(readonly=True)
    connection_status = fields.Selection([
        ('unknown', 'Not Checked'), ('connected', 'Connected'), ('failed', 'Failed')
    ], default='unknown', readonly=True)

    _sql_constraints = [
        ('techrar_config_name_unique', 'unique(name)', 'The configuration name must be unique.'),
    ]

    @api.constrains(
        'general_product_id', 'auto_confirm_orders',
        'auto_create_invoices', 'auto_register_payments',
        'myfatoorah_journal_id', 'tamara_journal_id', 'default_payment_journal_id',
        'sync_interval_minutes', 'sync_lookback_days', 'company_id'
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
                | config.default_payment_journal_id
            )
            if any(journal.company_id != config.company_id for journal in journals):
                raise UserError('All payment journals must belong to the configuration company.')
            if config.sync_interval_minutes < 1:
                raise UserError('Scheduled sync interval must be at least one minute.')
            if not 0 <= config.sync_lookback_days <= 30:
                raise UserError('Sync lookback must be between 0 and 30 days.')

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
        if not self.general_product_id:
            issues.append('Select the General Techrar Product.')
        if self.auto_register_payments and not self.myfatoorah_journal_id:
            issues.append('Select the MyFatoorah payment journal.')
        if self.auto_register_payments and not self.tamara_journal_id:
            issues.append('Select the Tamara payment journal.')
        return issues
