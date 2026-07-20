import requests
import json
import logging
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

    def action_sync_preview(self):
        self.ensure_one()
        config_param = self.env["ir.config_parameter"].sudo()
        access_key = config_param.get_param("bird.access_key")
        workspace_id = config_param.get_param("bird.workspace_id")

        if not access_key or not workspace_id:
            raise UserError("Please configure Bird API credentials in Settings first.")

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
