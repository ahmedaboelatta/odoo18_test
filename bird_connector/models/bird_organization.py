import requests
import json
import logging
import base64
from decimal import Decimal, InvalidOperation
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
        help='Bird Wallet UUID from Settings > Billing > Plan & payment > Wallet. If empty, Refresh Balance will select the main wallet automatically.',
    )
    wallet_name = fields.Char(string='Wallet Name', readonly=True)
    wallet_usage_raw = fields.Text(string='Wallet API Response', readonly=True)
    balance_source = fields.Selection([
        ('bird_wallet', 'Bird Wallet API'),
        ('bird_reporting', 'Bird Reporting API (Legacy Connector Logic)'),
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


    def _wallets_from_response(self, payload):
        """Normalize Bird's GET /organizations/{id}/wallets response to a wallet list."""
        if isinstance(payload, list):
            return [w for w in payload if isinstance(w, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("results", "items", "wallets", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [w for w in value if isinstance(w, dict)]
        # Be tolerant if Bird returns one wallet object directly.
        if payload.get("walletId") or payload.get("id"):
            return [payload]
        return []

    def _bird_money_to_decimal(self, money):
        """Convert Bird money format {amount, exponent} into a decimal major-unit amount."""
        if not isinstance(money, dict):
            return None, None
        raw_amount = money.get("amount")
        exponent = money.get("exponent", 0)
        currency = money.get("currencyCode") or money.get("currency")
        if raw_amount is None:
            return None, currency
        try:
            amount = Decimal(str(raw_amount)) * (Decimal(10) ** int(exponent or 0))
        except (InvalidOperation, ValueError, TypeError):
            return None, currency
        return amount, currency

    def _fetch_bird_wallets(self):
        self.ensure_one()
        wallet_key = (self.wallet_api_key or self.access_key or '').strip()
        if not wallet_key:
            raise UserError("Configure a Wallet API Key (or Workspace Access Key fallback) first.")
        if not self.bird_id:
            raise UserError(
                "Organization ID is required. Copy the UUID from Bird > Settings > Organization > Company profile."
            )

        url = "https://api.bird.com/organizations/%s/wallets" % self.bird_id.strip()
        headers = {
            "Authorization": "AccessKey %s" % wallet_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            response = requests.get(url, headers=headers, timeout=20)
        except Exception as exc:
            raise UserError("Bird Wallet request failed: %s" % exc)

        try:
            payload = response.json()
        except Exception:
            payload = {"raw": response.text[:4000]}

        # Keep the raw response for troubleshooting/audit.
        self.wallet_usage_raw = json.dumps(payload, ensure_ascii=False, indent=2, default=str)

        if response.status_code != 200:
            extra = ''
            if response.status_code == 403:
                extra = (
                    "\n\nThe request reached Bird but this key cannot read organization wallets. "
                    "Use the Organization-level API key that succeeds against GET /organizations/{organizationId}/wallets."
                )
            elif response.status_code == 401:
                extra = "\n\nThe Wallet API Key was not accepted by Bird. Check the key value/type."
            raise UserError(
                "Bird Wallet API failed (HTTP %s).\n\nEndpoint: %s\n\nResponse:\n%s%s"
                % (
                    response.status_code,
                    url,
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str)[:5000],
                    extra,
                )
            )
        return payload, url

    def action_sync_balance(self):
        self.ensure_one()
        payload, _url = self._fetch_bird_wallets()
        wallets = self._wallets_from_response(payload)
        if not wallets:
            raise UserError(
                "Bird returned HTTP 200, but no wallet records were found in the response. "
                "The raw payload is saved in Wallet API Response."
            )

        selected = None
        configured_wallet_id = (self.wallet_id or '').strip()
        if configured_wallet_id:
            selected = next(
                (w for w in wallets if str(w.get("walletId") or w.get("id") or '') == configured_wallet_id),
                None,
            )
        if not selected:
            selected = next((w for w in wallets if w.get("isMain") is True), None)
        if not selected and len(wallets) == 1:
            selected = wallets[0]
        if not selected:
            raise UserError(
                "Bird returned multiple wallets, but none matched Wallet ID and no main wallet was marked. "
                "Check Wallet API Response and configure the required Wallet ID."
            )

        balance, currency = self._bird_money_to_decimal(selected.get("balance"))
        if balance is None:
            raise UserError(
                "The selected Bird wallet does not contain a valid balance.amount/exponent structure. "
                "The raw payload is saved in Wallet API Response."
            )

        wallet_id = str(selected.get("walletId") or selected.get("id") or configured_wallet_id or '')
        wallet_name = selected.get("name") or ("Main wallet" if selected.get("isMain") else False)
        currency = currency or self.currency_code or "EUR"

        self.write({
            "wallet_id": wallet_id or self.wallet_id,
            "wallet_name": wallet_name,
            "wallet_balance": float(balance),
            "currency_code": currency,
            "last_balance_sync": fields.Datetime.now(),
            "balance_source": "bird_wallet",
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Balance Updated",
                "message": "%s: %.2f %s" % (wallet_name or "Bird wallet", float(balance), currency),
                "type": "success",
                "sticky": False,
                # Refresh the Odoo form data after the successful server-side write.
                # This avoids a manual browser/F5 refresh.
                "next": {"type": "ir.actions.client", "tag": "reload"},
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

    def _bird_template_effective_status(self, item):
        """Return a normalized Bird template/version status for ranking and UI."""
        status = str((item or {}).get("status") or (item or {}).get("state") or "draft").lower()
        approvals = []
        for content in (item or {}).get("platformContent") or []:
            if isinstance(content, dict):
                approvals += content.get("approvals") or []
        approval_status = next(
            (str(a.get("status") or "").lower() for a in approvals if isinstance(a, dict) and a.get("status")),
            "",
        )
        if approval_status:
            status = approval_status
        if status == "approved":
            status = "active"
        if status not in ("active", "pending", "draft", "rejected", "inactive"):
            status = "draft"
        return status

    def _upsert_synced_version(self, template, item):
        """Keep Bird versions under the canonical Odoo template instead of creating duplicate templates."""
        if not template or not isinstance(item, dict):
            return
        vid = item.get("id") or item.get("channelTemplateId") or item.get("resourceId") or item.get("versionId")
        if not vid:
            return
        status = self._bird_template_effective_status(item)
        raw_dt = item.get("updatedAt") or item.get("lastUpdated") or item.get("modifiedAt")
        parsed_dt = False
        if raw_dt:
            try:
                from datetime import datetime, timezone
                parsed_dt = datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00"))
                if parsed_dt.tzinfo:
                    parsed_dt = parsed_dt.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                parsed_dt = False
        vals = {
            "template_id": template.id,
            "bird_version_id": vid,
            "description": item.get("description") or item.get("name") or template.name,
            "status": status if status in ("draft", "pending", "active", "approved", "inactive", "rejected") else "draft",
            "publisher": item.get("publisherName") or item.get("publishedBy") or item.get("createdBy") or "",
            "last_updated": parsed_dt,
            "last_updated_by": item.get("updatedByName") or item.get("lastUpdatedBy") or item.get("updatedBy") or "",
            "is_current": bool(status == "active" or vid == template.bird_template_id or vid == template.active_resource_id),
            "raw_json": json.dumps(item, ensure_ascii=False, indent=2),
        }
        Version = self.env["bird.template.version"].sudo()
        existing = Version.search([("template_id", "=", template.id), ("bird_version_id", "=", vid)], limit=1)
        if existing:
            existing.write(vals)
        else:
            Version.create(vals)

    @api.model
    def _cron_sync_connector_data(self):
        """Scheduled sync controlled from Bird Connector > Configuration > Settings."""
        for org in self.sudo().search([("state", "=", "active")]):
            try:
                org.action_sync_workspaces_and_channels(target_workspace_id=org.workspace_id)
            except Exception:
                _logger.exception("Bird automatic connector sync failed for organization %s", org.display_name)

    @api.model
    def _cron_refresh_wallet_balances(self):
        """Scheduled wallet refresh controlled from Bird Connector Settings."""
        for org in self.sudo().search([("state", "=", "active")]):
            try:
                org.action_sync_balance()
            except Exception:
                _logger.exception("Bird automatic balance refresh failed for organization %s", org.display_name)

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

                    # One Bird Project can have many versions.  Keep one canonical
                    # bird.template record and store every other resource as a
                    # bird.template.version.  Prefer Active > Pending > Draft > Rejected/Inactive.
                    status_rank = {"active": 50, "pending": 40, "draft": 30, "rejected": 20, "inactive": 10}
                    template_list = sorted(
                        [x for x in template_list if isinstance(x, dict)],
                        key=lambda x: status_rank.get(self._bird_template_effective_status(x), 0),
                        reverse=True,
                    )
                    project_template_record = False

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
                            'status': self._bird_template_effective_status(template_info) if self._bird_template_effective_status(template_info) in ('active','draft','pending','rejected') else 'draft',
                            'source': 'bird',
                            'last_status_sync': fields.Datetime.now(),
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

                        template_fields = self.env['bird.template']._fields
                        workspace_field_name = 'workspace_id'
                        if 'workspace_id' not in template_fields:
                            if 'bird_workspace_id' in template_fields:
                                workspace_field_name = 'bird_workspace_id'
                            elif 'workspace' in template_fields:
                                workspace_field_name = 'workspace'

                        # The first (highest-ranked) version becomes the canonical
                        # template. Remaining resources are recorded as versions only.
                        if not project_template_record:
                            existing_template = self.env['bird.template'].sudo().search([
                                ('project_id', '=', proj_id),
                                (workspace_field_name, '=', local_workspace.id),
                            ], limit=1)
                            if not existing_template:
                                existing_template = self.env['bird.template'].sudo().search([
                                    ('bird_template_id', '=', template_id),
                                    (workspace_field_name, '=', local_workspace.id),
                                ], limit=1)

                            final_vals = {k: v for k, v in template_vals.items() if k in template_fields}
                            final_vals[workspace_field_name] = local_workspace.id

                            if existing_template:
                                existing_template.sudo().write(final_vals)
                                project_template_record = existing_template
                            else:
                                project_template_record = self.env['bird.template'].sudo().create(final_vals)
                                templates_created += 1

                        self._upsert_synced_version(project_template_record, template_info)

            except Exception as e:
                _logger.error(f"Templates Sync Error for project {proj_id}: {str(e)}")

        # Consolidate historical/project-version duplicates after a successful
        # synchronization.  The cleanup preserves message/version references.
        try:
            self.env['bird.template'].sudo()._cleanup_duplicate_projects()
        except Exception:
            _logger.exception('Bird template duplicate cleanup failed after sync')

        # Direct organization-form sync: refresh the current view so newly
        # synchronized channels/templates appear immediately. Internal callers
        # pass target_workspace_id and keep the tuple return for compatibility.
        if not target_workspace_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Bird Sync Completed",
                    "message": "Channels created: %s, Templates created: %s" % (channels_created, templates_created),
                    "type": "success",
                    "sticky": False,
                    "next": {"type": "ir.actions.client", "tag": "reload"},
                },
            }
        return channels_created, templates_created