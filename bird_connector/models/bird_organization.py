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
    channel_ids = fields.One2many('bird.channel', compute='_compute_bird_items', string='Channels')
    template_ids = fields.One2many('bird.template', compute='_compute_bird_items', string='Templates')

    @api.depends('workspace_ids.channel_ids', 'workspace_ids.template_ids')
    def _compute_bird_items(self):
        for rec in self:
            workspaces = rec.workspace_ids
            rec.channel_ids = workspaces.mapped('channel_ids')
            rec.template_ids = workspaces.mapped('template_ids')

    def action_test_connection(self):
        self.ensure_one()
        if not self.access_key or not self.workspace_id:
            raise UserError("Please ensure both Access Key and Workspace ID are filled.")
        url = f"https://api.bird.com/workspaces/{self.workspace_id}/connectors"
        headers = {"Authorization": f"AccessKey {self.access_key}", "Content-Type": "application/json"}
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {'title': 'Connection Successful', 'message': 'Successfully connected to Bird.com API.', 'type': 'success', 'sticky': False}
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

        local_workspace = self.env['bird.workspace'].sudo().search([('workspace_id', '=', self.workspace_id)], limit=1)
        if not local_workspace:
            local_workspace = self.env['bird.workspace'].sudo().create({
                'name': self.name or 'Bird Workspace',
                'workspace_id': self.workspace_id,
                'organization_id': self.id,
                'state': 'active'
            })

        channels_created = 0
        templates_created = 0

        # 1. Sync Channels from /connectors endpoint
        channels_url = f"https://api.bird.com/workspaces/{self.workspace_id}/connectors"
        try:
            c_response = requests.get(channels_url, headers=headers, timeout=15)
            _logger.info(f"Bird Channels API status: {c_response.status_code}")
            _logger.info(f"Bird Channels API raw response: {c_response.text[:2000]}")
            
            if c_response.status_code == 200:
                c_data = c_response.json()
                channels_list = c_data.get('results', []) if isinstance(c_data, dict) else c_data
                _logger.info(f"Bird Channels list length: {len(channels_list)}")
                
                for channel_info in channels_list:
                    _logger.info(f"Processing channel: {channel_info.get('platformId')} - {channel_info.get('id')}")
                    
                    platform_id = (channel_info.get('platformId') or channel_info.get('platform_id') or "").lower()
                    if platform_id != 'whatsapp':
                        _logger.info(f"Skipping non-whatsapp channel: {platform_id}")
                        continue

                    channel_id = channel_info.get('id') or channel_info.get('channelId')
                    if not channel_id:
                        _logger.info("Skipping channel with no id")
                        continue

                    existing_channel = self.env['bird.channel'].sudo().search([('channel_id', '=', channel_id)], limit=1)
                    _logger.info(f"Existing channel found: {bool(existing_channel)}")
                    
                    if not existing_channel:
                        self.env['bird.channel'].sudo().create({
                            'name': channel_info.get('name'),
                            'channel_id': channel_id,
                            'channel_type': 'whatsapp',
                            'workspace_id': local_workspace.id,
                            'state': 'active' if channel_info.get('status') in ['active', 'warning'] else 'inactive'
                        })
                        channels_created += 1
                        _logger.info(f"Created channel: {channel_info.get('name')}")
                    else:
                        _logger.info(f"Channel already exists: {channel_id}")
            else:
                _logger.error(f"Connectors API Error: {c_response.status_code} - {c_response.text}")
        except Exception as e:
            _logger.error(f"Channels Sync Exception: {str(e)}")

        # 2. Sync Templates from /studio/channelTemplates endpoint
        templates_url = f"https://api.bird.com/workspaces/{self.workspace_id}/studio/channelTemplates"
        try:
            t_response = requests.get(templates_url, headers=headers, timeout=15)
            _logger.info(f"Bird Templates API status: {t_response.status_code}")
            _logger.info(f"Bird Templates API raw response: {t_response.text[:2000]}")
            
            if t_response.status_code == 200:
                t_data = t_response.json()
                templates_list = t_data.get('results', []) if isinstance(t_data, dict) else t_data
                _logger.info(f"Bird Templates list length: {len(templates_list)}")
                
                for template_info in templates_list:
                    _logger.info(f"Processing template: {template_info.get('id')}")
                    
                    template_id = template_info.get('id') or template_info.get('templateId') or template_info.get('projectId')
                    if not template_id:
                        _logger.info("Skipping template with no id")
                        continue

                    existing_template = self.env['bird.template'].sudo().search([('bird_template_id', '=', template_id)], limit=1)
                    _logger.info(f"Existing template found: {bool(existing_template)}")
                    
                    if not existing_template:
                        self.env['bird.template'].sudo().create({
                            'name': template_info.get('name') or template_info.get('id'),
                            'bird_template_id': template_id,
                            'project_id': template_info.get('projectId'),
                            'version': template_info.get('version'),
                            'locale': template_info.get('locale', 'en'),
                            'status': 'active' if template_info.get('status') == 'active' else 'draft',
                            'workspace_id': local_workspace.id
                        })
                        templates_created += 1
                        _logger.info(f"Created template: {template_info.get('name')}")
                    else:
                        _logger.info(f"Template already exists: {template_id}")
            else:
                _logger.error(f"Studio Templates API Error: {t_response.status_code} - {t_response.text}")
        except Exception as e:
            _logger.error(f"Templates Sync Exception: {str(e)}")

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
