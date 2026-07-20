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

    def action_sync_workspaces_channels(self):
        self.ensure_one()
        if not self.access_key or not self.workspace_id:
            raise UserError("Please configure Access Key and Workspace ID before syncing.")

        headers = {
            "Authorization": f"AccessKey {self.access_key}",
            "Content-Type": "application/json",
        }

        try:
            # 1. Ensure workspace record exists
            workspace = self.env["bird.workspace"].search([
                ("workspace_id", "=", self.workspace_id),
                ("organization_id", "=", self.id),
            ], limit=1)

            if not workspace:
                workspace = self.env["bird.workspace"].create({
                    "name": f"{self.name} Workspace",
                    "workspace_id": self.workspace_id,
                    "organization_id": self.id,
                    "state": "active",
                })

            # 2. Fetch WhatsApp channels for this workspace
            channels_url = f"https://api.bird.com/workspaces/{self.workspace_id}/channels"
            channels_response = requests.get(channels_url, headers=headers, timeout=15)
            if channels_response.status_code != 200:
                raise UserError(f"Channels Sync Failed: HTTP {channels_response.status_code} - {channels_response.text}")

            channels_data = channels_response.json()
            channels_list = channels_data if isinstance(channels_data, list) else channels_data.get("channels", channels_data.get("data", []))

            created_channels = 0
            updated_channels = 0

            for item in channels_list:
                platform_id = (item.get("platformId") or item.get("platform_id") or "").lower()
                if platform_id != "whatsapp":
                    continue

                channel_id = item.get("id") or item.get("channelId")
                if not channel_id:
                    continue

                existing = self.env["bird.channel"].search([
                    ("channel_id", "=", channel_id),
                    ("workspace_id", "=", workspace.id),
                ], limit=1)

                vals = {
                    "name": item.get("name", channel_id),
                    "channel_id": channel_id,
                    "channel_type": "whatsapp",
                    "workspace_id": workspace.id,
                    "state": "connected" if item.get("status") in [True, "active", "connected", 1] else "disconnected",
                    "connected_account": item.get("connectedAccount") or item.get("connected_account") or "",
                    "last_activity": fields.Datetime.now(),
                }

                if existing:
                    existing.write(vals)
                    updated_channels += 1
                else:
                    self.env["bird.channel"].create(vals)
                    created_channels += 1

            # 3. Fetch templates for this workspace
            templates_url = f"https://api.bird.com/workspaces/{self.workspace_id}/templates"
            templates_response = requests.get(templates_url, headers=headers, timeout=15)
            if templates_response.status_code == 200:
                templates_data = templates_response.json()
                templates_list = templates_data if isinstance(templates_data, list) else templates_data.get("templates", templates_data.get("data", []))

                created_templates = 0
                updated_templates = 0

                for item in templates_list:
                    template_id = item.get("id") or item.get("templateId") or item.get("projectId")
                    if not template_id:
                        continue

                    existing = self.env["bird.template"].search([
                        ("bird_template_id", "=", template_id),
                        ("workspace_id", "=", workspace.id),
                    ], limit=1)

                    variables = item.get("variables") or item.get("parameters") or {}
                    if isinstance(variables, (dict, list)):
                        variables = json.dumps(variables)
                    else:
                        variables = ""

                    content = item.get("content", {}) or {}
                    body = content.get("body", {}).get("text", "") or item.get("body", "")
                    header_text = content.get("header", {}).get("text", "") or item.get("headerText", "")
                    footer_text = content.get("footer", {}).get("text", "") or item.get("footerText", "")

                    status = item.get("status", "draft")
                    if isinstance(status, str):
                        status = status.lower()
                    if status not in ["active", "draft", "pending"]:
                        status = "draft"

                    vals = {
                        "name": item.get("name", template_id),
                        "workspace_id": workspace.id,
                        "template_type": item.get("type", "channelTemplate"),
                        "bird_template_id": template_id,
                        "project_id": item.get("projectId", ""),
                        "version": item.get("version", "1"),
                        "locale": item.get("locale", "en"),
                        "status": status,
                        "body": body,
                        "header_text": header_text,
                        "footer_text": footer_text,
                        "variables": variables,
                    }

                    if existing:
                        existing.write(vals)
                        updated_templates += 1
                    else:
                        self.env["bird.template"].create(vals)
                        created_templates += 1
            else:
                _logger.error(f"Bird Templates Sync Error: {templates_response.status_code} - {templates_response.text}")
                created_templates = 0
                updated_templates = 0

            message = (
                f"Sync complete: {created_channels} channels created, {updated_channels} updated, "
                f"{created_templates} templates created, {updated_templates} updated."
            )
            _logger.info(message)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Sync Successful",
                    "message": message,
                    "type": "success",
                    "sticky": False,
                },
            }

        except Exception as e:
            _logger.error(f"Bird Sync Failure: {str(e)}")
            raise UserError(f"Sync Failed: {str(e)}")
