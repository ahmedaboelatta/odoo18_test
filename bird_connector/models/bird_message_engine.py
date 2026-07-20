import requests
import json
import logging
from odoo import models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BirdMessageEngine(models.AbstractModel):
    _name = "bird.message.engine"
    _description = "Bird API Message Engine"

    @api.model
    def action_send_whatsapp_template(self, channel_id, receiver_mobile, project_id, version_id, locale="en", parameters=None):
        access_key = self.env["ir.config_parameter"].sudo().get_param("bird.access_key")
        workspace_id = self.env["ir.config_parameter"].sudo().get_param("bird.workspace_id")

        if not access_key or not workspace_id:
            raise UserError("Please configure Bird API credentials in settings first.")

        url = f"https://api.bird.com/workspaces/{workspace_id}/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"AccessKey {access_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "receiver": {
                "contacts": [
                    {
                        "identifierValue": receiver_mobile,
                    }
                ]
            },
            "template": {
                "projectId": project_id,
                "version": version_id,
                "locale": locale,
            },
        }

        if parameters:
            payload["template"]["parameters"] = parameters

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code in [200, 201, 202]:
                _logger.info(f"Bird WhatsApp message successfully initialized for {receiver_mobile}")
                return response.json()
            else:
                _logger.error(f"Bird API Error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            _logger.error(f"Bird Connection Failure: {str(e)}")
            return False
