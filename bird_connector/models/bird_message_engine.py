import json
import logging
import re

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
    def _normalize_receiver(self, receiver):
        value = (receiver or "").strip()
        value = re.sub(r"[\s\-()]+", "", value)
        if not value:
            raise UserError("Receiver mobile number is required.")
        if not re.fullmatch(r"\+?\d{8,15}", value):
            raise UserError("Receiver must be a valid international number, e.g. +9665XXXXXXXX.")
        if not value.startswith("+"):
            value = "+" + value
        return value

    @api.model
    def _normalize_parameters(self, parameters):
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
            normalized.append({
                "type": item.get("type") or "string",
                "key": key,
                "value": "" if value is None else str(value),
            })
        return normalized

    @api.model
    def _validate_channel(self, channel):
        if not channel or not channel.exists():
            raise UserError("Please select a valid Bird channel.")
        if channel.channel_type != "whatsapp":
            raise UserError("The selected channel is not a WhatsApp channel.")
        workspace = channel.workspace_id
        organization = workspace.organization_id
        if not organization or not organization.access_key:
            raise UserError("The workspace organization has no Bird API access key configured.")
        if not workspace.workspace_id:
            raise UserError("The Bird Workspace ID is missing.")
        if not channel.channel_id:
            raise UserError("The Bird Channel ID is missing.")
        return workspace, organization

    @api.model
    def _create_log_and_send(self, channel, receiver, message_type, payload, **extra_vals):
        workspace, organization = self._validate_channel(channel)
        receiver = self._normalize_receiver(receiver)

        vals = {
            "channel_id": channel.id,
            "receiver_mobile": receiver,
            "message_type": message_type,
            "request_payload": self.env["bird.api.service"].pretty_json(payload),
            "reference": payload.get("reference") or False,
            "status": "queued",
        }
        vals.update(extra_vals)
        log = self.env["bird.message.log"].sudo().create(vals)

        path = f"/workspaces/{workspace.workspace_id}/channels/{channel.channel_id}/messages"
        result = self.env["bird.api.service"].post(
            path=path,
            access_key=organization.access_key,
            payload=payload,
            timeout=30,
        )
        log._apply_api_result(result, sending=True)
        return log

    @api.model
    def send_whatsapp_template(self, channel, receiver, template, parameters=None, locale=None, reference=None):
        self._validate_channel(channel)
        if not template or not template.exists():
            raise UserError("Please select a valid Bird template.")
        if template.workspace_id != channel.workspace_id:
            raise UserError("The selected template and channel must belong to the same workspace.")
        if not template.project_id or not template.version:
            raise UserError("Template Project ID and Version are required before sending.")

        receiver = self._normalize_receiver(receiver)
        effective_locale = locale or template.locale or "en"
        bird_parameters = self._normalize_parameters(parameters)
        raw_version = (template.version or "").strip()
        send_version = raw_version if len(raw_version) >= 32 and "-" in raw_version else "latest"

        payload = {
            "receiver": {"contacts": [{"identifierValue": receiver}]},
            "template": {
                "projectId": template.project_id,
                "version": send_version,
                "locale": effective_locale,
            },
        }
        if bird_parameters:
            payload["template"]["parameters"] = bird_parameters
        if reference:
            payload["reference"] = reference

        return self._create_log_and_send(
            channel=channel,
            receiver=receiver,
            message_type="template",
            payload=payload,
            template_id=template.id,
            project_id=template.project_id,
            version_id=send_version,
            locale=effective_locale,
            parameters=json.dumps(bird_parameters, indent=2, ensure_ascii=False),
        )

    @api.model
    def send_whatsapp_text(self, channel, receiver, text, reference=None):
        if not (text or "").strip():
            raise UserError("Message text is required.")
        receiver = self._normalize_receiver(receiver)
        payload = {
            "receiver": {"contacts": [{"identifierValue": receiver}]},
            "body": {"type": "text", "text": {"text": text.strip()}},
        }
        if reference:
            payload["reference"] = reference
        return self._create_log_and_send(
            channel=channel,
            receiver=receiver,
            message_type="text",
            payload=payload,
            body_text=text.strip(),
        )

    @api.model
    def send_whatsapp_image(self, channel, receiver, media_url, caption=None, reference=None):
        if not (media_url or "").strip():
            raise UserError("Image URL is required.")
        receiver = self._normalize_receiver(receiver)
        image = {"images": [{"mediaUrl": media_url.strip()}]}
        if caption:
            image["text"] = caption.strip()
        payload = {
            "receiver": {"contacts": [{"identifierValue": receiver}]},
            "body": {"type": "image", "image": image},
        }
        if reference:
            payload["reference"] = reference
        return self._create_log_and_send(
            channel=channel,
            receiver=receiver,
            message_type="image",
            payload=payload,
            body_text=(caption or "").strip() or False,
            media_url=media_url.strip(),
        )

    @api.model
    def send_whatsapp_file(self, channel, receiver, media_url, filename=None, caption=None, reference=None):
        if not (media_url or "").strip():
            raise UserError("File URL is required.")
        receiver = self._normalize_receiver(receiver)
        file_item = {"mediaUrl": media_url.strip()}
        if filename:
            file_item["filename"] = filename.strip()
        file_body = {"files": [file_item]}
        if caption:
            file_body["text"] = caption.strip()
        payload = {
            "receiver": {"contacts": [{"identifierValue": receiver}]},
            "body": {"type": "file", "file": file_body},
        }
        if reference:
            payload["reference"] = reference
        return self._create_log_and_send(
            channel=channel,
            receiver=receiver,
            message_type="file",
            payload=payload,
            body_text=(caption or "").strip() or False,
            media_url=media_url.strip(),
            filename=(filename or "").strip() or False,
        )

    # Backward-compatible wrapper for existing custom code calling the old method.
    @api.model
    def action_send_whatsapp_template(
        self, channel_id, receiver_mobile, project_id, version_id, locale="en",
        parameters=None, access_key=None, workspace_id=None,
    ):
        channel = self.env["bird.channel"].sudo().search([("channel_id", "=", channel_id)], limit=1)
        template = self.env["bird.template"].sudo().search([
            ("project_id", "=", project_id),
            ("version", "=", str(version_id)),
        ], limit=1)
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

        raw_access_key = access_key or self.env["ir.config_parameter"].sudo().get_param("bird.access_key")
        raw_workspace_id = workspace_id or self.env["ir.config_parameter"].sudo().get_param("bird.workspace_id")
        if not raw_access_key or not raw_workspace_id:
            raise UserError("Please configure Bird API credentials before sending messages.")
        payload = {
            "receiver": {"contacts": [{"identifierValue": receiver_mobile}]},
            "template": {"projectId": project_id, "version": version_id, "locale": locale},
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
