import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BirdMessageEngine(models.AbstractModel):
    _name = "bird.message.engine"
    _description = "Bird API Message Engine"

    @api.model
    def _extract_message_id(self, data):
        if not isinstance(data, dict):
            return False
        return data.get("id") or data.get("messageId") or data.get("message_id") or False

    @api.model
    def _extract_status(self, data):
        if not isinstance(data, dict):
            return False
        status = data.get("status")
        if isinstance(status, dict):
            return status.get("code") or status.get("value") or status.get("status")
        return status

    @api.model
    def _normalize_parameters(self, parameters):
        """Normalize parameter input to Bird's [{type,key,value}] shape."""
        normalized = []
        for item in parameters or []:
            if not item:
                continue
            if isinstance(item, models.BaseModel):
                item = {
                    "type": getattr(item, "parameter_type", "string"),
                    "key": getattr(item, "key", False),
                    "value": getattr(item, "value", False),
                }
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if not key:
                continue
            value = item.get("value")
            normalized.append(
                {
                    "type": item.get("type") or "string",
                    "key": key,
                    "value": "" if value is None else str(value),
                }
            )
        return normalized

    @api.model
    def send_whatsapp_template(
        self,
        channel,
        receiver,
        template,
        parameters=None,
        locale=None,
        reference=None,
    ):
        """Send one WhatsApp template through Bird Channels API.

        Returns the created bird.message.log record. API failures are logged and
        returned with status=failed instead of raising, preserving the audit trail.
        """
        if not channel or not channel.exists():
            raise UserError("Please select a valid Bird channel.")
        if channel.channel_type != "whatsapp":
            raise UserError("The selected channel is not a WhatsApp channel.")
        if not template or not template.exists():
            raise UserError("Please select a valid Bird template.")
        if template.workspace_id != channel.workspace_id:
            raise UserError("The selected template and channel must belong to the same workspace.")
        if not receiver:
            raise UserError("Receiver mobile number is required.")

        workspace = channel.workspace_id
        organization = workspace.organization_id
        if not organization or not organization.access_key:
            raise UserError("The workspace organization has no Bird API access key configured.")
        if not workspace.workspace_id:
            raise UserError("The Bird Workspace ID is missing.")
        if not channel.channel_id:
            raise UserError("The Bird Channel ID is missing.")
        if not template.project_id or not template.version:
            raise UserError("Template Project ID and Version are required before sending.")

        effective_locale = locale or template.locale or "en"
        bird_parameters = self._normalize_parameters(parameters)

        payload = {
            "receiver": {
                "contacts": [
                    {
                        "identifierValue": receiver.strip(),
                    }
                ]
            },
            "template": {
                "projectId": template.project_id,
                "version": template.version,
                "locale": effective_locale,
            },
        }
        if bird_parameters:
            payload["template"]["parameters"] = bird_parameters
        if reference:
            payload["reference"] = reference

        log = self.env["bird.message.log"].sudo().create(
            {
                "channel_id": channel.id,
                "receiver_mobile": receiver.strip(),
                "message_type": "template",
                "template_id": template.id,
                "project_id": template.project_id,
                "version_id": template.version,
                "locale": effective_locale,
                "parameters": json.dumps(bird_parameters, indent=2, ensure_ascii=False),
                "request_payload": json.dumps(payload, indent=2, ensure_ascii=False),
                "reference": reference or False,
                "status": "queued",
            }
        )

        path = f"/workspaces/{workspace.workspace_id}/channels/{channel.channel_id}/messages"
        result = self.env["bird.api.service"].post(
            path=path,
            access_key=organization.access_key,
            payload=payload,
            timeout=30,
        )

        data = result.get("data") or {}
        vals = {
            "http_status": result.get("status_code") or 0,
            "bird_response": self.env["bird.api.service"].pretty_json(data),
            "bird_message_id": self._extract_message_id(data),
            "bird_status": self._extract_status(data) or False,
        }

        if result.get("ok"):
            vals.update(
                {
                    "status": "sent",
                    "send_date": fields.Datetime.now(),
                    "error_message": False,
                }
            )
            _logger.info("Bird WhatsApp template initialized for %s", receiver)
        else:
            vals.update(
                {
                    "status": "failed",
                    "failed_at": fields.Datetime.now(),
                    "error_message": result.get("error") or "Unknown Bird API error",
                }
            )

        log.sudo().write(vals)
        return log

    # Backward-compatible wrapper for existing custom code calling the old method.
    @api.model
    def action_send_whatsapp_template(
        self,
        channel_id,
        receiver_mobile,
        project_id,
        version_id,
        locale="en",
        parameters=None,
        access_key=None,
        workspace_id=None,
    ):
        channel = self.env["bird.channel"].sudo().search([("channel_id", "=", channel_id)], limit=1)
        template = self.env["bird.template"].sudo().search(
            [
                ("project_id", "=", project_id),
                ("version", "=", str(version_id)),
            ],
            limit=1,
        )
        if channel and template:
            log = self.send_whatsapp_template(
                channel=channel,
                receiver=receiver_mobile,
                template=template,
                parameters=parameters,
                locale=locale,
            )
            if log.status == "failed":
                return False
            try:
                return json.loads(log.bird_response or "{}")
            except Exception:
                return {"id": log.bird_message_id, "status": log.bird_status}

        # Compatibility fallback for callers passing raw IDs not synced locally.
        raw_access_key = access_key or self.env["ir.config_parameter"].sudo().get_param("bird.access_key")
        raw_workspace_id = workspace_id or self.env["ir.config_parameter"].sudo().get_param("bird.workspace_id")
        if not raw_access_key or not raw_workspace_id:
            raise UserError("Please configure Bird API credentials before sending messages.")

        payload = {
            "receiver": {"contacts": [{"identifierValue": receiver_mobile}]},
            "template": {
                "projectId": project_id,
                "version": version_id,
                "locale": locale,
            },
        }
        normalized = self._normalize_parameters(parameters)
        if normalized:
            payload["template"]["parameters"] = normalized

        result = self.env["bird.api.service"].post(
            path=f"/workspaces/{raw_workspace_id}/channels/{channel_id}/messages",
            access_key=raw_access_key,
            payload=payload,
        )
        return result.get("data") if result.get("ok") else False
