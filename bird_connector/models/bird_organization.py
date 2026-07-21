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

        # 2. Sync Templates from /studio/channelTemplates endpoint with full field mapping
        templates_url = f"https://api.bird.com/workspaces/{api_workspace_id}/studio/channelTemplates"
        try:
            t_response = requests.get(templates_url, headers=headers, timeout=15)
            _logger.info(f"Bird Templates API status: {t_response.status_code}")
            
            if t_response.status_code == 200:
                t_data = t_response.json()
                templates_list = t_data.get('results', []) if isinstance(t_data, dict) else t_data
                _logger.info(f"Bird Templates list length: {len(templates_list)}")
                
                for template_info in templates_list:
                    template_id = template_info.get('id')
                    if not template_id:
                        continue

                    existing_template = self.env['bird.template'].sudo().search([('bird_template_id', '=', template_id)], limit=1)
                    
                    t_name = template_info.get('name') or template_info.get('description') or template_id
                    deployments = template_info.get('deployments', [])
                    for dep in deployments:
                        if dep.get('key') == 'whatsappTemplateName' and dep.get('value'):
                            t_name = dep.get('value')
                            break

                    raw_locale = template_info.get('defaultLocale', 'en')
                    sanitized_locale = raw_locale.replace('-', '_') if raw_locale else 'en'
                    
                    locale_field = self.env['bird.template']._fields.get('locale')
                    allowed_locales = [sel[0] for sel in locale_field.selection] if locale_field and hasattr(locale_field, 'selection') else []
                    if allowed_locales and sanitized_locale not in allowed_locales:
                        short_locale = sanitized_locale.split('_')[0]
                        if short_locale in allowed_locales:
                            sanitized_locale = short_locale
                        else:
                            sanitized_locale = allowed_locales[0] if allowed_locales else 'en'

                    body_text = ""
                    footer_text = ""
                    header_image = ""
                    platform_content = template_info.get('platformContent', [])
                    if platform_content:
                        blocks = platform_content[0].get('blocks', [])
                        for block in blocks:
                            role = block.get('role')
                            if role == 'body':
                                body_text = block.get('text', {}).get('text', '')
                            elif role == 'footer':
                                footer_text = block.get('text', {}).get('text', '')
                            elif role == 'header' and block.get('type') == 'image':
                                header_image = block.get('image', {}).get('url', '')

                    counts = template_info.get('counts', {})
                    active_count = counts.get('active', 0) if isinstance(counts, dict) else 0
                    inactive_count = counts.get('inactive', 0) if isinstance(counts, dict) else 0
                    draft_count = counts.get('draft', 0) if isinstance(counts, dict) else 0
                    pending_count = counts.get('pending', 0) if isinstance(counts, dict) else 0

                    template_vals = {
                        'name': t_name,
                        'bird_template_id': template_id,
                        'project_id': template_info.get('projectId', ''),
                        'version': template_info.get('version', '1'),
                        'locale': sanitized_locale,
                        'status': 'active' if template_info.get('status') == 'active' else 'draft',
                        'workspace_id': local_workspace.id,
                        'description': template_info.get('description', ''),
                        'supported_platforms': str(template_info.get('supportedPlatforms', [])),
                        'locales': template_info.get('locales', template_info.get('defaultLocale', '')),
                        'active_count': active_count,
                        'inactive_count': inactive_count,
                        'draft_count': draft_count,
                        'pending_count': pending_count,
                        'scope': template_info.get('scope', ''),
                        'active_resource_id': template_info.get('activeResourceId', ''),
                        'is_cloneable': template_info.get('isCloneable', False),
                        'short_links_enabled': template_info.get('shortLinks', {}).get('enabled', False),
                        'short_links_domain': template_info.get('shortLinks', {}).get('domain', ''),
                        'platform_info': json.dumps(template_info.get('platformInfo', {})),
                        'platform_content': json.dumps(template_info.get('platformContent', [])),
                        'deployments': json.dumps(template_info.get('deployments', [])),
                        'styles': json.dumps(template_info.get('styles', [])),
                        'variables': json.dumps(template_info.get('variables', [])),
                        'generic_content': json.dumps(template_info.get('genericContent', [])),
                        'preview_body_text': body_text,
                        'preview_footer_text': footer_text,
                        'preview_header_image': header_image,
                    }

                    if existing_template:
                        existing_template.write(template_vals)
                        templates_created += 1
                        _logger.info(f"Updated template: {t_name}")
                    else:
                        self.env['bird.template'].sudo().create(template_vals)
                        templates_created += 1
                        _logger.info(f"Created template: {t_name}")
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