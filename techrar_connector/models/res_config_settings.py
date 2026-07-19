from odoo import fields, models
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    techrar_api_url = fields.Char(
        string='Techrar API Base URL',
        config_parameter='techrar.api_base_url',
        default='https://api.techrar.com',
    )
    techrar_api_token = fields.Char(
        string='Techrar API Token',
        config_parameter='techrar.api_token',
        password=True,
    )
    techrar_app_id = fields.Char(
        string='Techrar App ID',
        config_parameter='techrar.app_id',
        default='3',
    )

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
                raise UserError(f"Connection failed with status {response.status_code}: {response.text}")
        except requests.exceptions.Timeout:
            raise UserError('Connection to Techrar API timed out.')
        except requests.exceptions.ConnectionError:
            raise UserError('Cannot connect to Techrar API. Please check the URL and network.')
        except Exception as e:
            raise UserError(f"Connection error: {str(e)}")
