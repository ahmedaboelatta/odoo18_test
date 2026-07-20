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

    def action_sync_workspaces_and_channels(self, target_workspace_id=False):
        self.ensure_one()
        
        access_key = self.access_key
        api_workspace_id = target_workspace_id or self.workspace_id
        
        if not access_key or not api_workspace_id:
            raise UserError("Missing API Access Key or Workspace ID configuration.")

        headers = {
            "Authorization": f"AccessKey {access_key}",
            "Content-Type": "application/json"
        }

        local_workspace = self.env['bird.workspace'].sudo().search([('workspace_id', '=', api_workspace_id)], limit=1)
        if not local_workspace:
            local_workspace = self.env['bird.workspace'].sudo().create({
                'name': self.name or 'Bird Workspace',
                'workspace_id': api_workspace_id,
                'organization_id': self.id,
                'state': 'active'
            })

        channels_created = 0
        templates_created = 0

        # 1. مزامنة القنوات بناءً على هيكل الـ Connectors JSON الفعلي
        channels_url = f"https://api.bird.com/workspaces/{api_workspace_id}/connectors"
        try:
            c_response = requests.get(channels_url, headers=headers, timeout=15)
            if c_response.status_code == 200:
                c_data = c_response.json()
                for channel_info in c_data.get('results', []):
                    # الفحص بناءً على الحقل الفعلي القادم من السيرفر connectorTemplateRef
                    template_ref = channel_info.get('connectorTemplateRef', '')
                    if template_ref and 'whatsapp' in template_ref:
                        # جلب الـ channelId الصحيح من داخل كائن channel الفرعي
                        channel_data = channel_info.get('channel', {})
                        actual_channel_id = channel_data.get('channelId') or channel_info.get('id')
                        
                        existing_channel = self.env['bird.channel'].sudo().search([('channel_id', '=', actual_channel_id)], limit=1)
                        if not existing_channel:
                            self.env['bird.channel'].sudo().create({
                                'name': channel_info.get('name', 'WhatsApp Channel'),
                                'channel_id': actual_channel_id,
                                'channel_type': 'whatsapp',
                                'workspace_id': local_workspace.id,
                                'state': 'active'
                            })
                            channels_created += 1
        except Exception as e:
            _logger.error(f"Channels Sync Error: {str(e)}")

        # 2. مزامنة القوالب
        templates_url = f"https://api.bird.com/workspaces/{api_workspace_id}/studio/channelTemplates"
        try:
            t_response = requests.get(templates_url, headers=headers, timeout=15)
            if t_response.status_code == 200:
                t_data = t_response.json()
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
                            'workspace_id': local_workspace.id
                        })
                        templates_created += 1
        except Exception as e:
            _logger.error(f"Templates Sync Error: {str(e)}")

        return channels_created, templates_created