import requests
import json
import logging
import base64
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class BirdOrganization(models.Model):
    _name = 'bird.organization'
    _description = 'Bird Organization'

    name = fields.Char(string='Organization Name', required=True)
    bird_id = fields.Char(string='Organization ID', help='Bird Organization UUID from Settings > Organization > Company profile.')
    access_key = fields.Char(string='Workspace Access Key', required=True, help='Bird Workspace Access Key used for workspaces, channels, templates and messages.')
    wallet_api_key = fields.Char(string='Wallet API Key', help='Organization-level Bird API key used only for Wallet/Reporting API requests. Keep separate from the Workspace Access Key when Bird requires organization-level financial permissions.')
    wallet_id = fields.Char(
        string='Wallet ID',
        help='Bird Wallet UUID from Settings > Billing > Plan & payment > Wallet.',
    )
    wallet_usage_raw = fields.Text(string='Wallet API Response', readonly=True)
    balance_source = fields.Selection([
        ('bird_reporting', 'Bird Reporting API'),
        ('manual', 'Manual'),
    ], string='Balance Source', readonly=True)
    workspace_id = fields.Char(string='Default Workspace ID', required=True, help='Primary Bird Workspace UUID used by this connector.')
    wallet_balance = fields.Float(string='Wallet Balance', digits=(16, 2))
    currency_code = fields.Char(string='Currency Code', default='EUR')
    low_balance_threshold = fields.Float(string='Low Balance Threshold', default=5.0)
    last_balance_sync = fields.Datetime(string='Last Balance Sync', readonly=True)
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


    def _extract_balance_from_wallet_response(self, payload):
        """Return (amount, currency) only when Bird gives an unambiguous balance field.

        The Reporting API response can evolve, so we deliberately do not treat a generic
        usage/total amount as remaining balance.
        """
        self.ensure_one()
        candidates = []

        def walk(value, path=""):
            if isinstance(value, dict):
                for key, val in value.items():
                    key_l = str(key).lower()
                    child = f"{path}.{key}" if path else str(key)
                    if key_l in ("balance", "currentbalance", "availablebalance", "remainingbalance", "walletbalance"):
                        candidates.append((child, val, value))
                    walk(val, child)
            elif isinstance(value, list):
                for idx, val in enumerate(value):
                    walk(val, f"{path}[{idx}]")

        walk(payload)
        for _path, value, parent in candidates:
            amount = None
            currency = None
            if isinstance(value, (int, float)):
                amount = float(value)
            elif isinstance(value, str):
                try:
                    amount = float(value)
                except Exception:
                    pass
            elif isinstance(value, dict):
                raw = value.get("amount") or value.get("value")
                try:
                    amount = float(raw) if raw is not None else None
                except Exception:
                    pass
                currency = value.get("currency") or value.get("currencyCode")
            if amount is not None:
                if not currency and isinstance(parent, dict):
                    currency = parent.get("currency") or parent.get("currencyCode")
                return amount, (currency or self.currency_code or "EUR")
        return None, None

    def _fetch_bird_wallet(self):
        self.ensure_one()
        wallet_key = (self.wallet_api_key or self.access_key or '').strip()
        if not wallet_key:
            raise UserError("Configure a Wallet API Key (or Workspace Access Key fallback) first.")
        if not self.bird_id:
            raise UserError(
                "Bird Organization ID is required for the modern Wallet API. "
                "Enter the Organization UUID in the Bird ID field."
            )
        if not self.wallet_id:
            raise UserError("Wallet ID is required. Copy it from the Bird wallet page URL.")

        url = (
            "https://api.bird.com/organizations/%s/reporting/accounting/wallets/%s/usage"
            % (self.bird_id.strip(), self.wallet_id.strip())
        )
        headers = {
            "Authorization": "AccessKey %s" % wallet_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            # Bird documents Wallet Metrics as POST. An empty JSON body is intentional.
            response = requests.post(url, headers=headers, json={}, timeout=20)
        except Exception as exc:
            raise UserError("Bird Wallet request failed: %s" % exc)

        try:
            payload = response.json()
        except Exception:
            payload = {"raw": response.text[:4000]}

        self.wallet_usage_raw = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        if response.status_code not in (200, 201):
            extra = ''
            if response.status_code == 403:
                extra = (
                    "\n\nThe request reached the correct Organization/Wallet endpoint, but Bird denied the action. "
                    "Use an Organization-level Wallet API Key with Organization Finance Management / Reporting access."
                )
            elif response.status_code == 401:
                extra = "\n\nThe Wallet API Key was not accepted by Bird. Check the key value/type."
            raise UserError(
                "Bird Wallet API failed (HTTP %s).\n\nEndpoint: %s\n\nResponse:\n%s%s"
                % (response.status_code, url, json.dumps(payload, ensure_ascii=False, indent=2, default=str)[:5000], extra)
            )
        return payload

    def action_sync_balance(self):
        self.ensure_one()
        payload = self._fetch_bird_wallet()
        amount, currency = self._extract_balance_from_wallet_response(payload)
        if amount is None:
            raise UserError(
                "Bird Wallet API responded successfully, but the documented usage response did not contain "
                "an unambiguous current/available balance field. The complete response was saved in "
                "Wallet API Response so we do not display a usage amount as if it were remaining balance."
            )
        self.write({
            "wallet_balance": amount,
            "currency_code": currency,
            "last_balance_sync": fields.Datetime.now(),
            "balance_source": "bird_reporting",
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Balance Updated",
                "message": "Current Bird wallet balance: %.2f %s" % (amount, currency),
                "type": "success",
                "sticky": False,
            },
        }

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

        # 2. Sync Touchpoints Templates with Full Details
        projects_url = f"https://api.bird.com/workspaces/{api_workspace_id}/projects"
        project_ids = []
        try:
            p_response = requests.get(projects_url, headers=headers, timeout=15)
            if p_response.status_code == 200:
                p_data = p_response.json()
                project_list = p_data.get('results') or p_data.get('items') or []
                if not project_list and isinstance(p_data, list):
                    project_list = p_data
                project_ids = [p.get('id') for p in project_list if p.get('id')]
        except Exception as e:
            _logger.error(f"Projects Fetch Error: {str(e)}")

        locale_field = self.env['bird.template']._fields.get('locale')
        allowed_locales = [sel[0] for sel in locale_field.selection] if locale_field and hasattr(locale_field, 'selection') else []

        for proj_id in project_ids:
            templates_url = f"https://api.bird.com/workspaces/{api_workspace_id}/projects/{proj_id}/channel-templates"
            try:
                t_response = requests.get(templates_url, headers=headers, timeout=15)
                _logger.info(f"Bird Touchpoints Templates API status for project {proj_id}: {t_response.status_code}")
                
                if t_response.status_code == 200:
                    t_data = t_response.json()
                    template_list = t_data.get('results') or t_data.get('items') or []
                    if not template_list and isinstance(t_data, list):
                        template_list = t_data

                    for template_info in template_list:
                        template_id = template_info.get('id')
                        if not template_id:
                            continue

                        t_name = template_info.get('name') or template_info.get('description') or template_id
                        deployments = template_info.get('deployments', [])
                        for dep in deployments:
                            if dep.get('key') == 'whatsappTemplateName' and dep.get('value'):
                                t_name = dep.get('value')
                                break

                        raw_locale = template_info.get('defaultLocale', 'en')
                        sanitized_locale = raw_locale.replace('-', '_') if raw_locale else 'en'
                        if allowed_locales and sanitized_locale not in allowed_locales:
                            short_locale = sanitized_locale.split('_')[0]
                            sanitized_locale = short_locale if short_locale in allowed_locales else (allowed_locales[0] if allowed_locales else 'en')

                        # تعريف متغيرات المعاينة مسبقاً لمنع UnboundLocalError
                        body_text = ""
                        footer_text = ""
                        header_image_url = ""
                        preview_header_image_binary = False

                        platform_content = template_info.get('platformContent', [])
                        if platform_content and isinstance(platform_content, list):
                            blocks = platform_content[0].get('blocks', [])
                            for block in blocks:
                                b_type = block.get('type')
                                role = block.get('role')
                                
                                # 1. Check for nested header object inside the block
                                header_obj = block.get('header', {})
                                if header_obj and isinstance(header_obj, dict):
                                    if header_obj.get('type') == 'image':
                                        img_obj = header_obj.get('image', {})
                                        header_image_url = img_obj.get('mediaUrl') or img_obj.get('url', '')

                                # 2. Standard Templates (Text / Image)
                                if b_type in ['text', 'image']:
                                    if role == 'body':
                                        body_text = block.get('text', {}).get('text', '')
                                    elif role == 'footer':
                                        footer_text = block.get('text', {}).get('text', '')
                                    elif role == 'header' and b_type == 'image':
                                        img_obj = block.get('image', {})
                                        header_image_url = img_obj.get('mediaUrl') or img_obj.get('url', '')

                                # Interactive WhatsApp Flow Templates
                                elif b_type == 'whatsapp-flow':
                                    flow_data = block.get('whatsappFlow', {})
                                    body_text = flow_data.get('body', {}).get('text', {}).get('text', '')
                                    footer_text = flow_data.get('footer', {}).get('text', {}).get('text', '')
                                    
                                    header_obj = flow_data.get('header', {})
                                    if header_obj and header_obj.get('type') == 'image':
                                        img_obj = header_obj.get('image', {})
                                        header_image_url = img_obj.get('mediaUrl') or img_obj.get('url', '')

                        # تحميل الصورة بواسطة AccessKey وتغليفها كـ Base64
                        if header_image_url:
                            try:
                                img_res = requests.get(header_image_url, headers=headers, timeout=10)
                                if img_res.status_code == 200:
                                    preview_header_image_binary = base64.b64encode(img_res.content)
                            except Exception as e:
                                _logger.error(f"Preview image download error: {e}")

                        # تجهيز قائمة الحقول والتفاصيل كاملة
                        template_vals = {
                            'name': t_name,
                            'bird_template_id': template_id,
                            'project_id': template_info.get('projectId', proj_id),
                            'version': str(template_info.get('version', '1')),
                            'locale': sanitized_locale,
                            'status': template_info.get('status') if template_info.get('status') in ('active','draft','pending','rejected') else 'draft',
                            'source': 'bird',
                            'description': template_info.get('description', ''),
                            'supported_platforms': str(template_info.get('supportedPlatforms', [])),
                            'is_cloneable': template_info.get('isCloneable', False),
                            'short_links_enabled': template_info.get('shortLinks', {}).get('enabled', False),
                            'short_links_domain': template_info.get('shortLinks', {}).get('domain', ''),
                            'platform_info': json.dumps(template_info.get('platformInfo', {}), indent=2),
                            'platform_content': json.dumps(template_info.get('platformContent', []), indent=2),
                            'deployments': json.dumps(template_info.get('deployments', []), indent=2),
                            'styles': json.dumps(template_info.get('styles', []), indent=2),
                            'variables': json.dumps(template_info.get('variables', []), indent=2),
                            'generic_content': json.dumps(template_info.get('genericContent', []), indent=2),
                            'preview_body_text': body_text,
                            'preview_footer_text': footer_text,
                            'preview_header_image': preview_header_image_binary,
                        }
                        # Use the centralized resilient preview parser. It handles
                        # image/text headers, RTL body/footer and interactive buttons.
                        template_vals.update(
                            self.env['bird.template']._extract_preview_from_payload(template_info, access_key)
                        )

                        # فحص وجود القالب للتحديث أو الإنشاء
                        existing_template = self.env['bird.template'].sudo().search([('bird_template_id', '=', template_id)], limit=1)
                        template_fields = self.env['bird.template']._fields
                        workspace_field_name = 'workspace_id'
                        if 'workspace_id' not in template_fields:
                            if 'bird_workspace_id' in template_fields:
                                workspace_field_name = 'bird_workspace_id'
                            elif 'workspace' in template_fields:
                                workspace_field_name = 'workspace'

                        # تنقية الحقول للتأكد من وجودها بالموديل قبل الكتابة
                        final_vals = {}
                        for k, v in template_vals.items():
                            if k in template_fields:
                                final_vals[k] = v

                        final_vals[workspace_field_name] = local_workspace.id

                        if existing_template:
                            existing_template.sudo().write(final_vals)
                        else:
                            self.env['bird.template'].sudo().create(final_vals)
                            templates_created += 1

            except Exception as e:
                _logger.error(f"Templates Sync Error for project {proj_id}: {str(e)}")

        return channels_created, templates_created