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
    preview_header_text = fields.Char(string="Preview Header Text")
    preview_body_text = fields.Text(string="Preview Body Text")
    preview_footer_text = fields.Char(string="Preview Footer Text")
    preview_button_1 = fields.Char(string="Preview Button 1")
    preview_button_2 = fields.Char(string="Preview Button 2")
    preview_button_3 = fields.Char(string="Preview Button 3")

    @api.model
    def _extract_preview_from_payload(self, template_info, access_key=False):
        """Build a resilient WhatsApp-style preview from Bird Touchpoints JSON.

        Bird has more than one template block shape (standard blocks, WhatsApp
        flow blocks, generic content, actions/buttons).  We intentionally parse
        by semantic role and recurse through nested structures so the preview
        continues to work as Bird adds wrappers around the same content.
        """
        body_text = ""
        footer_text = ""
        header_text = ""
        header_image_url = ""
        buttons = []

        def first_text(value):
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, dict):
                # Bird commonly nests text as {text: {text: "..."}}.
                for key in ("text", "value", "title", "label", "name"):
                    if key in value:
                        found = first_text(value.get(key))
                        if found:
                            return found
            return ""

        def image_url(value):
            if not isinstance(value, dict):
                return ""
            for key in ("mediaUrl", "url", "src", "sourceUrl"):
                if value.get(key):
                    return value.get(key)
            for key in ("image", "media", "file", "content"):
                found = image_url(value.get(key))
                if found:
                    return found
            return ""

        def add_button(value):
            label = first_text(value) if isinstance(value, (dict, str)) else ""
            if label and label not in buttons and len(buttons) < 3:
                buttons.append(label)

        def walk(node, parent_key=""):
            nonlocal body_text, footer_text, header_text, header_image_url
            if isinstance(node, list):
                for item in node:
                    walk(item, parent_key)
                return
            if not isinstance(node, dict):
                return

            role = str(node.get("role") or "").lower()
            b_type = str(node.get("type") or "").lower()

            if role == "body":
                text = first_text(node.get("text") or node.get("body") or node)
                if text:
                    body_text = text
            elif role == "footer":
                text = first_text(node.get("text") or node.get("footer") or node)
                if text:
                    footer_text = text
            elif role == "header":
                if b_type in ("image", "media"):
                    header_image_url = image_url(node) or header_image_url
                else:
                    text = first_text(node.get("text") or node.get("header") or node)
                    if text:
                        header_text = text

            # WhatsApp Flow block shape.
            flow = node.get("whatsappFlow")
            if isinstance(flow, dict):
                text = first_text(flow.get("body"))
                if text:
                    body_text = text
                text = first_text(flow.get("footer"))
                if text:
                    footer_text = text
                header = flow.get("header")
                if isinstance(header, dict):
                    if str(header.get("type") or "").lower() == "image":
                        header_image_url = image_url(header) or header_image_url
                    else:
                        text = first_text(header)
                        if text:
                            header_text = text

            # Generic explicit header object.
            header = node.get("header")
            if isinstance(header, dict):
                if str(header.get("type") or "").lower() == "image":
                    header_image_url = image_url(header) or header_image_url
                elif not header_text:
                    header_text = first_text(header) or header_text

            for key in ("buttons", "actions"):
                value = node.get(key)
                if isinstance(value, list):
                    for item in value:
                        add_button(item)

            # Some payloads represent each button as a block/action.
            if role in ("button", "action") or b_type in ("button", "quick-reply", "url", "call"):
                add_button(node)

            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    walk(value, key)

        walk(template_info.get("platformContent") or [])
        walk(template_info.get("genericContent") or [])

        # Fall back to top-level content used by some Bird APIs.
        content = template_info.get("content") or {}
        if not body_text:
            body_text = first_text(content.get("body")) or first_text(template_info.get("body"))
        if not footer_text:
            footer_text = first_text(content.get("footer")) or first_text(template_info.get("footerText"))
        if not header_text:
            header_text = first_text(content.get("header")) or first_text(template_info.get("headerText"))

        preview_header_image_binary = False
        if header_image_url:
            try:
                headers = {"Authorization": f"AccessKey {access_key}"} if access_key else {}
                img_res = requests.get(header_image_url, headers=headers, timeout=12)
                if img_res.status_code in (401, 403) and headers:
                    img_res = requests.get(header_image_url, timeout=12)
                if img_res.status_code == 200 and img_res.content:
                    preview_header_image_binary = base64.b64encode(img_res.content)
            except Exception as exc:
                _logger.warning("Bird preview image download failed: %s", exc)

        return {
            "preview_header_image": preview_header_image_binary,
            "preview_header_text": header_text,
            "preview_body_text": body_text,
            "preview_footer_text": footer_text,
            "preview_button_1": buttons[0] if len(buttons) > 0 else False,
            "preview_button_2": buttons[1] if len(buttons) > 1 else False,
            "preview_button_3": buttons[2] if len(buttons) > 2 else False,
        }

    def action_open_send_message(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Send Bird Message",
            "res_model": "bird.send.message.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "bird.template",
                "active_id": self.id,
                "default_template_id": self.id,
            },
        }

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
                if status not in ["active", "draft", "pending", "rejected"]:
                    status = "draft"

                vals = {
                    "name": item.get("name", template_id),
                    "source": "bird",
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
                vals.update(self._extract_preview_from_payload(item, access_key))

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
