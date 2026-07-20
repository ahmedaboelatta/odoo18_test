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
            
            template_fields = self.env['bird.template']._fields
            w_field = 'workspace_id'
            if 'workspace_id' not in template_fields and 'bird_workspace_id' in template_fields:
                w_field = 'bird_workspace_id'
            elif 'workspace_id' not in template_fields and 'workspace' in template_fields:
                w_field = 'workspace'
                
            rec.template_ids = self.env['bird.template'].sudo().search([(w_field, 'in', workspaces.ids)])

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

        # 1. Sync Channels
        channels_url = f"https://api.bird.com/workspaces/{api_workspace_id}/channels"
        try:
            c_response = requests.get(channels_url, headers=headers, timeout=15)
            if c_response.status_code == 200:
                c_data = c_response.json()
                for channel_info in c_data.get('results', []):
                    if channel_info.get('platformId') == 'whatsapp':
                        existing_channel = self.env['bird.channel'].sudo().search([('channel_id', '=', channel_info.get('id'))], limit=1)
                        if not existing_channel:
                            state_field = self.env['bird.channel']._fields.get('state')
                            allowed_states = [sel[0] for sel in state_field.selection] if state_field and hasattr(state_field, 'selection') else []
                            
                            target_state = 'active'
                            if allowed_states:
                                if 'active' not in allowed_states:
                                    if 'Active' in allowed_states:
                                        target_state = 'Active'
                                    elif 'enabled' in allowed_states:
                                        target_state = 'enabled'
                                    elif 'Enabled' in allowed_states:
                                        target_state = 'Enabled'
                                    else:
                                        target_state = allowed_states[0]

                            self.env['bird.channel'].sudo().create({
                                'name': channel_info.get('name', 'WhatsApp Channel'),
                                'channel_id': channel_info.get('id'),
                                'channel_type': 'whatsapp',
                                'workspace_id': local_workspace.id,
                                'state': target_state
                            })
                            channels_created += 1
        except Exception as e:
            _logger.error(f"Channels Sync Error: {str(e)}")

        # 2. Sync Templates (دعم كامل لكافة أشكال رد سيرفر Bird المتوقعة)
        templates_url = f"https://api.bird.com/workspaces/{api_workspace_id}/templates"
        try:
            t_response = requests.get(templates_url, headers=headers, timeout=15)
            _logger.info(f"Bird Templates API status: {t_response.status_code}")
            
            if t_response.status_code == 200:
                t_data = t_response.json()
                
                # استخراج قائمة التمبلتس باختلاف مفتاح الرد (results أو items أو مصفوفة مباشرة)
                template_list = []
                if isinstance(t_data, list):
                    template_list = t_data
                elif isinstance(t_data, dict):
                    template_list = t_data.get('results') or t_data.get('items') or []
                
                _logger.info(f"Bird Templates list length: {len(template_list)}")

                for template_info in template_list:
                    # تفادي الأخطاء إذا كانت البيانات قادمة بشكل غير متوقع
                    template_id = template_info.get('id') or template_info.get('bird_template_id')
                    if not template_id:
                        continue
                        
                    existing_template = self.env['bird.template'].sudo().search([('bird_template_id', '=', template_id)], limit=1)
                    if not existing_template:
                        template_fields = self.env['bird.template']._fields
                        workspace_field_name = 'workspace_id'
                        if 'workspace_id' not in template_fields:
                            if 'bird_workspace_id' in template_fields:
                                workspace_field_name = 'bird_workspace_id'
                            elif 'workspace' in template_fields:
                                workspace_field_name = 'workspace'

                        template_vals = {
                            'name': template_info.get('name') or template_id,
                            'bird_template_id': template_id,
                            'project_id': template_info.get('projectId'),
                            'version': template_info.get('version'),
                            'locale': template_info.get('locale', 'en'),
                            'status': 'active' if template_info.get('status') in ['active', 'APPROVED'] else 'draft',
                        }
                        template_vals[workspace_field_name] = local_workspace.id

                        self.env['bird.template'].sudo().create(template_vals)
                        templates_created += 1
        except Exception as e:
            _logger.error(f"Templates Sync Error: {str(e)}")

        return channels_created, templates_created