import requests
import json
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class BirdOrganization(models.Model):
    _name = 'bird.organization'
    _description = 'Bird Organization'

    name = fields.Char(string='Organization Name', required=True)
    bird_id = fields.Char(string='Bird ID')
    access_key = fields.Char(string='Access Key', required=True)
    workspace_id = fields.Char(string='Workspace ID', required=True)
    wallet_balance = fields.Float(string='Wallet Balance', digits=(16, 2))
    currency_code = fields.Char(string='Currency Code', default='EUR')
    low_balance_threshold = fields.Float(string='Low Balance Threshold', default=5.0)
    state = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ], string='Status', default='active')
    
    workspace_ids = fields.One2many('bird.workspace', 'organization_id', string='Workspaces')

    def action_test_connection(self):
        """
        Verified connection test using fields from the current form view.
        """
        self.ensure_one()
        
        if not self.access_key or not self.workspace_id:
            raise UserError("Please ensure both Access Key and Workspace ID are filled.")

        # الرابط المعتمد والناجح من تجربة بوستمان
        url = f"https://api.bird.com/workspaces/{self.workspace_id}/channels"
        
        headers = {
            "Authorization": f"AccessKey {self.access_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                # عرض رسالة النجاح المطابقة للمطلوب
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Connection Successful',
                        'message': f'Successfully connected to Bird.com API. Workspace verified.',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(f"Connection Failed: HTTP {response.status_code} - {response.text}")
                
        except Exception as e:
            raise UserError(f"Network Connection Error: {str(e)}")
