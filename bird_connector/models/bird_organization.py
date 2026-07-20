import requests
import json
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BirdOrganization(models.Model):
    _name = "bird.organization"
    _description = "Bird Organization"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Organization Name", required=True, tracking=True)
    state = fields.Selection(
        [("active", "Active"), ("inactive", "Inactive")],
        string="State",
        default="active",
        tracking=True,
    )
    wallet_balance = fields.Float(string="Wallet Balance", digits=(12, 2), tracking=True)
    currency_code = fields.Char(string="Currency Code", default="EUR", tracking=True)
    low_balance_threshold = fields.Float(
        string="Low Balance Threshold", digits=(12, 2), default=5.0
    )
    bird_id = fields.Char(string="Bird ID", tracking=True)
    workspace_ids = fields.One2many(
        "bird.workspace", "organization_id", string="Workspaces"
    )

    def action_test_connection(self):
        self.ensure_one()
        config_param = self.env["ir.config_parameter"].sudo()
        access_key = config_param.get_param("bird.access_key")
        workspace_id = config_param.get_param("bird.workspace_id")

        if not access_key or not workspace_id:
            raise UserError(
                "Please configure Bird API credentials in Settings before testing connection."
            )

        url = f"https://api.bird.com/workspaces/{workspace_id}/organizations/{self.bird_id or ''}"
        headers = {
            "Authorization": f"AccessKey {access_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code in [200, 201, 202]:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Connection Successful",
                        "message": "Successfully connected to Bird.com API...",
                        "type": "success",
                        "sticky": False,
                    },
                }
            else:
                _logger.error(
                    f"Bird API Connection Error: {response.status_code} - {response.text}"
                )
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Connection Failed",
                        "message": f"HTTP {response.status_code}: {response.text}",
                        "type": "danger",
                        "sticky": True,
                    },
                }
        except Exception as e:
            _logger.error(f"Bird Connection Failure: {str(e)}")
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Connection Failed",
                    "message": str(e),
                    "type": "danger",
                    "sticky": True,
                },
            }
