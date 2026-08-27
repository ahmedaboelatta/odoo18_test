from odoo import fields, models, api
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
    auto_confirm_orders = fields.Boolean(string='Automatically Confirm Orders', default=False)
    auto_create_invoices = fields.Boolean(string='Automatically Create Invoices', default=False)
    auto_register_payments = fields.Boolean(string='Automatically Register Payments', default=False)
    last_successful_sync = fields.Datetime(readonly=True)
    last_connection_at = fields.Datetime(readonly=True)
    connection_status = fields.Selection([
        ('unknown', 'Not Checked'), ('connected', 'Connected'), ('failed', 'Failed')
    ], default='unknown', readonly=True)

    _sql_constraints = [
        ('techrar_config_name_unique', 'unique(name)', 'The configuration name must be unique.'),
    ]

    @api.constrains('auto_confirm_orders', 'auto_create_invoices', 'auto_register_payments')
    def _check_automation_sequence(self):
        for config in self:
            if config.auto_create_invoices and not config.auto_confirm_orders:
                raise UserError('Automatic invoicing requires automatic order confirmation.')
            if config.auto_register_payments and not config.auto_create_invoices:
                raise UserError('Automatic payment registration requires automatic invoicing.')

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
                self.write({'last_connection_at': fields.Datetime.now(), 'connection_status': 'connected'})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Connection Successful',
                        'message': 'Successfully connected to Techrar API.',
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
