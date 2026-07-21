import requests
import json
import logging
import base64
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BirdTemplate(models.Model):
    _name = "bird.template"
    _description = "Bird Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Template Name", required=True, tracking=True)
    workspace_id = fields.Many2one(
        "bird.workspace", string="Workspace", required=True, ondelete="cascade"
    )
    template_type = fields.Selection(
        [("channelTemplate", "Channel Template")],
        string="Template Type",
        default="channelTemplate",
        required=True,
    )
    bird_template_id = fields.Char(string="Bird Template ID", tracking=True)
    project_id = fields.Char(string="Project ID", required=True, tracking=True)
    locale = fields.Selection(
        [("en", "English"), ("ar", "Arabic")],
        string="Default Locale",
        default="en",
        required=True,
    )
    status = fields.Selection(
        [("active", "Active"), ("draft", "Draft"), ("pending", "Pending")],
        string="Status",
        default="draft",
        tracking=True,
    )
    version = fields.Char(string="Version", required=True, tracking=True)
    body = fields.Text(string="Template Body", tracking=True)
    header_text = fields.Char(string="Header Text", tracking=True)
    footer_text = fields.Char(string="Footer Text", tracking=True)
    variables = fields.Text(string="Variables", help="JSON mapping of variable placeholders")
    organization_id = fields.Many2one(
        "bird.organization",
        string="Organization",
        related="workspace_id.organization_id",
        store=True,
    )

    description = fields.Text(string="Description")
    supported_platforms = fields.Char(string="Supported Platforms")
    locales = fields.Char(string="Locales")
    active_count = fields.Integer(string="Active Count")
    inactive_count = fields.Integer(string="Inactive Count")
    draft_count = fields.Integer(string="Draft Count")
    pending_count = fields.Integer(string="Pending Count")
    scope = fields.Char(string="Scope")
    active_resource_id = fields.Char(string="Active Resource ID")
    is_cloneable = fields.Boolean(string="Is Cloneable")
    short_links_enabled = fields.Boolean(string="Short Links Enabled")
    short_links_domain = fields.Char(string="Short Links Domain")

    platform_info = fields.Text(string="Platform Info")
    platform_content = fields.Text(string="Platform Content")
    deployments = fields.Text(string="Deployments")
    styles = fields.Text(string="Styles")
    generic_content = fields.Text(string="Generic Content")

    preview_header_image = fields.Binary(string="Preview Header Image")
    preview_body_text = fields.Text(string="Preview Body Text")
    preview_footer_text = fields.Char(string="Preview Footer Text")

    def action_sync_template(self):
        self.ensure_one()
        workspace = self.workspace_id if hasattr(self, 'workspace_id') else getattr(self, 'bird_workspace_id', False)
        if not workspace or not workspace.organization_id:
            raise UserError("Cannot find the associated Organization to retrieve the API Key.")
        
        org = workspace.organization_id
        org.action_sync_workspaces_and_channels(target_workspace_id=workspace.workspace_id)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Template Synced',
                'message': f'Template "{self.name}" updated successfully.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_sync_preview(self):
        self.ensure_one()
        if not self.workspace_id or not self.workspace_id.organization_id:
            raise UserError("Template must be linked to a workspace with an organization.")

        org = self.workspace_id.organization_id
        access_key = org.access_key
        workspace_id = org.workspace_id

        if not access_key or not workspace_id:
            raise UserError("Please configure API credentials on the linked organization.")

        url = (
            f"https://api.bird.com/workspaces/{workspace_id}/templates/{self.bird_template_id}"
        )
        headers = {
            "Authorization": f"AccessKey {access_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                preview_text = data.get("content", {}).get("body", {}).get("text", "")
                self.body = preview_text
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Sync Successful",
                        "message": "Template preview synced successfully.",
                        "type": "success",
                        "sticky": False,
                    },
                }
            else:
                _logger.error(
                    f"Bird Template Sync Error: {response.status_code} - {response.text}"
                )
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Sync Failed",
                        "message": f"HTTP {response.status_code}: {response.text}",
                        "type": "danger",
                        "sticky": True,
                    },
                }
        except Exception as e:
            _logger.error(f"Bird Template Sync Failure: {str(e)}")
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Sync Failed",
                    "message": str(e),
                    "type": "danger",
                    "sticky": True,
                },
            }

    @api.model
    def action_sync_templates(self, workspace_id):
        workspace = self.env["bird.workspace"].browse(workspace_id)
        if not workspace or not workspace.organization_id:
            raise UserError("Invalid workspace or missing organization.")

        org = workspace.organization_id
        access_key = org.access_key
        bird_workspace_id = org.workspace_id

        if not access_key or not bird_workspace_id:
            raise UserError("Please configure API credentials on the organization.")

        url = f"https://api.bird.com/workspaces/{bird_workspace_id}/templates"
        headers = {
            "Authorization": f"AccessKey {access_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                raise UserError(f"Template Sync Failed: HTTP {response.status_code} - {response.text}")

            data = response.json()
            templates_data = data if isinstance(data, list) else data.get("templates", data.get("data", []))

            created = 0
            updated = 0

            for item in templates_data:
                template_id = item.get("id") or item.get("templateId") or item.get("projectId")
                if not template_id:
                    continue

                existing = self.search([
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
                    "description": item.get("description", ""),
                    "supported_platforms": str(item.get("supportedPlatforms", [])),
                    "locales": item.get("locales", item.get("defaultLocale", "")),
                    "scope": item.get("scope", ""),
                    "active_resource_id": item.get("activeResourceId", ""),
                    "is_cloneable": item.get("isCloneable", False),
                    "short_links_enabled": item.get("shortLinks", {}).get("enabled", False),
                    "short_links_domain": item.get("shortLinks", {}).get("domain", ""),
                    "platform_info": json.dumps(item.get("platformInfo", {})),
                    "platform_content": json.dumps(item.get("platformContent", [])),
                    "deployments": json.dumps(item.get("deployments", [])),
                    "styles": json.dumps(item.get("styles", [])),
                    "generic_content": json.dumps(item.get("genericContent", [])),
                }

                platform_content = item.get("platformContent", [])
                body_text = ""
                footer_text = ""
                header_image_url = ""
                preview_header_image_binary = False
                
                if platform_content and isinstance(platform_content, list):
                    blocks = platform_content[0].get("blocks", [])
                    for block in blocks:
                        b_type = block.get("type")
                        role = block.get("role")
                        
                        # 1. Check for nested header object inside the block
                        header_obj = block.get('header', {})
                        if header_obj and isinstance(header_obj, dict):
                            if header_obj.get('type') == 'image':
                                img_obj = header_obj.get('image', {})
                                header_image_url = img_obj.get('mediaUrl') or img_obj.get('url', '')

                        # 2. Standard Blocks (Text / Image)
                        if b_type in ['text', 'image']:
                            if role == 'body':
                                body_text = block.get('text', {}).get('text', '')
                            elif role == 'footer':
                                footer_text = block.get('text', {}).get('text', '')
                            elif role == 'header' and b_type == 'image':
                                img_obj = block.get('image', {})
                                header_image_url = img_obj.get('mediaUrl') or img_obj.get('url', '')

                        # 3. Interactive WhatsApp Flow Templates
                        elif b_type == 'whatsapp-flow':
                            flow_data = block.get('whatsappFlow', {})
                            body_text = flow_data.get('body', {}).get('text', {}).get('text', '')
                            footer_text = flow_data.get('footer', {}).get('text', {}).get('text', '')
                            
                            flow_header = flow_data.get('header', {})
                            if flow_header and flow_header.get('type') == 'image':
                                img_obj = flow_header.get('image', {})
                                header_image_url = img_obj.get('mediaUrl') or img_obj.get('url', '')

                # Download & encode image with API Authorization headers
                if header_image_url:
                    try:
                        img_res = requests.get(header_image_url, headers={"Authorization": f"AccessKey {access_key}"}, timeout=10)
                        if img_res.status_code == 200:
                            preview_header_image_binary = base64.b64encode(img_res.content)
                    except Exception as e:
                        _logger.error(f"Preview image download error: {e}")

                vals.update({
                    "preview_body_text": body_text,
                    "preview_footer_text": footer_text,
                    "preview_header_image": preview_header_image_binary,
                })

                counts = item.get("counts", {})
                if isinstance(counts, dict):
                    vals.update({
                        "active_count": counts.get("active", 0),
                        "inactive_count": counts.get("inactive", 0),
                        "draft_count": counts.get("draft", 0),
                        "pending_count": counts.get("pending", 0),
                    })

                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    self.create(vals)
                    created += 1

            message = f"Template sync complete: {created} created, {updated} updated."
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
            _logger.error(f"Bird Template Sync Failure: {str(e)}")
            raise UserError(f"Template Sync Failed: {str(e)}")
