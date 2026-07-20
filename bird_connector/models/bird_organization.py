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

        url = f"https://api.bird.com/workspaces/{self.workspace_id}/channels"
        headers = {
            "Authorization": f"AccessKey {self.access_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                raise UserError(f"Sync Failed: HTTP {response.status_code} - {response.text}")

            data = response.json()
            channels_data = data if isinstance(data, list) else data.get("channels", data.get("data", []))

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

            created_channels = 0
            updated_channels = 0

            for item in channels_data:
                channel_id = item.get("id") or item.get("channelId")
                if not channel_id:
                    continue

                existing = self.env["bird.channel"].search([
                    ("channel_id", "=", channel_id),
                    ("workspace_id", "=", workspace.id),
                ], limit=1)

                channel_type = item.get("platformId") or item.get("channel_type") or "other"
                if isinstance(channel_type, str):
                    channel_type = channel_type.lower()
                    if channel_type not in ["whatsapp", "email", "sms", "telegram"]:
                        channel_type = "other"

                vals = {
                    "name": item.get("name", channel_id),
                    "channel_id": channel_id,
                    "channel_type": channel_type,
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

            message = f"Sync complete: {created_channels} created, {updated_channels} updated."
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
