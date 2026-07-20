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

    def action_sync_workspaces_and_channels(self):
        self.ensure_one()
        if not self.access_key or not self.workspace_id:
            raise UserError("Please ensure both Access Key and Workspace ID are filled.")

        headers = {
            "Authorization": f"AccessKey {self.access_key}",
            "Content-Type": "application/json"
        }

        # 1. Sync Workspace
        workspace_url = f"https://api.bird.com/workspaces/{self.workspace_id}"
        try:
            w_response = requests.get(workspace_url, headers=headers, timeout=15)
            if w_response.status_code == 200:
                w_data = w_response.json()
                workspace = self.env['bird.workspace'].sudo().search([('workspace_id', '=', self.workspace_id)], limit=1)
                if not workspace:
                    workspace = self.env['bird.workspace'].sudo().create({
                        'name': w_data.get('name', 'Bird Workspace'),
                        'workspace_id': self.workspace_id,
                        'organization_id': self.id,
                        'state': 'active'
                    })
            else:
                raise UserError(f"Failed to fetch Workspace details: {w_response.text}")
        except Exception as e:
            raise UserError(f"Workspace Sync Error: {str(e)}")

        channels_created = 0
        templates_created = 0

        # 2. Sync Channels within this Workspace
        channels_url = f"https://api.bird.com/workspaces/{self.workspace_id}/channels"
        try:
            c_response = requests.get(channels_url, headers=headers, timeout=15)
            if c_response.status_code == 200:
                c_data = c_response.json()
                # Bird returns results inside a list/array named 'results'
                for channel_info in c_data.get('results', []):
                    if channel_info.get('platformId') == 'whatsapp':
                        existing_channel = self.env['bird.channel'].sudo().search([('channel_id', '=', channel_info.get('id'))], limit=1)
                        if not existing_channel:
                            self.env['bird.channel'].sudo().create({
                                'name': channel_info.get('name'),
                                'channel_id': channel_info.get('id'),
                                'channel_type': 'whatsapp',
                                'workspace_id': workspace.id,
                                'state': 'active' if channel_info.get('status') in ['active', 'warning'] else 'inactive'
                            })
                            channels_created += 1
        except Exception as e:
            _logger.error(f"Channels Sync Sub-Error: {str(e)}")

        # 3. Sync Templates within this Workspace
        templates_url = f"https://api.bird.com/workspaces/{self.workspace_id}/templates"
        try:
            t_response = requests.get(templates_url, headers=headers, timeout=15)
            if t_response.status_code == 200:
                t_data = t_response.json()
                # Bird returns templates inside 'results' array
                for template_info in t_data.get('results', []):
                    existing_template = self.env['bird.template'].sudo().search([('bird_template_id', '=', template_info.get('id'))], limit=1)
                    if not existing_template:
                        self.env['bird.template'].sudo().create({
                            'name': template_info.get('name') or template_info.get('id'),
                            'bird_template_id': template_info.get('id'),
                            'project_id': template_info.get('projectId'),
                            'version': template_info.get('version'),
                            'locale': template_info.get('locale', 'en'),
                            'status': 'active' if template_info.get('status') == 'active' else 'draft',
                            'workspace_id': workspace.id
                        })
                        templates_created += 1
        except Exception as e:
            _logger.error(f"Templates Sync Sub-Error: {str(e)}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Successful',
                'message': f'Sync complete: {channels_created} channels created, {templates_created} templates created.',
                'type': 'success',
                'sticky': False,
            }
        }
