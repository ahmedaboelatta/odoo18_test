import json
import re
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class BirdTemplate(models.Model):
    _inherit = "bird.template"

    # Relax sync-only requirements so a user can create a local Draft first.
    project_id = fields.Char(string="Project ID", required=False, tracking=True, copy=False)
    version = fields.Char(string="Version", required=False, default="latest", tracking=True, copy=False)
    bird_template_id = fields.Char(string="Bird Template ID", tracking=True, copy=False)
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending"),
            ("active", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        tracking=True,
    )

    source = fields.Selection(
        [("odoo", "Created in Odoo"), ("bird", "Synced from Bird")],
        default="odoo",
        required=True,
        tracking=True,
    )
    api_name = fields.Char(
        string="Template API Name",
        help="Lowercase technical WhatsApp template name sent for approval.",
        tracking=True,
    )
    channel_id = fields.Many2one(
        "bird.channel",
        string="WhatsApp Channel",
        domain="[('workspace_id', '=', workspace_id), ('channel_type', '=', 'whatsapp')]",
        tracking=True,
    )
    channel_group_id = fields.Char(
        string="Bird Channel Group ID",
        help="WhatsApp Business Account / channel group used by Bird for template deployment.",
        copy=False,
    )
    category = fields.Selection(
        [("MARKETING", "Marketing"), ("UTILITY", "Utility"), ("AUTHENTICATION", "Authentication")],
        default="UTILITY",
        required=True,
        tracking=True,
    )
    header_type = fields.Selection(
        [("none", "None"), ("text", "Text"), ("image", "Image")],
        default="none",
        required=True,
        tracking=True,
    )
    header_image = fields.Binary(string="Header Image", attachment=True)
    header_image_filename = fields.Char(string="Header Image Filename")
    header_media_url = fields.Char(
        string="Header Public Media URL",
        help="Bird/Meta needs a retrievable media reference for image header approval."
    )
    variable_line_ids = fields.One2many(
        "bird.template.variable", "template_id", string="Variables", copy=True
    )
    button_ids = fields.One2many(
        "bird.template.button", "template_id", string="Buttons", copy=True
    )
    rejection_reason = fields.Text(string="Rejection Reason", readonly=True, copy=False)
    approval_details = fields.Text(string="Approval Details", readonly=True, copy=False)
    last_status_sync = fields.Datetime(string="Last Status Sync", readonly=True, copy=False)
    submitted_at = fields.Datetime(string="Submitted At", readonly=True, copy=False)

    _sql_constraints = [
        ("bird_template_workspace_api_name_uniq", "unique(workspace_id, api_name)", "Template API Name must be unique per workspace."),
    ]

    @api.onchange("name")
    def _onchange_name_api_name(self):
        if self.source == "odoo" and self.name and not self.api_name:
            value = self.name.strip().lower()
            value = re.sub(r"[^a-z0-9_]+", "_", value)
            value = re.sub(r"_+", "_", value).strip("_")
            self.api_name = value[:512]

    @api.onchange("workspace_id")
    def _onchange_workspace_template_channel(self):
        if self.channel_id and self.channel_id.workspace_id != self.workspace_id:
            self.channel_id = False

    @api.onchange("button_ids", "button_ids.text")
    def _onchange_button_preview(self):
        for rec in self:
            labels = rec.button_ids.sorted("sequence").mapped("text")[:3]
            rec.preview_button_1 = labels[0] if len(labels) > 0 else False
            rec.preview_button_2 = labels[1] if len(labels) > 1 else False
            rec.preview_button_3 = labels[2] if len(labels) > 2 else False

    @api.onchange("body", "header_text", "footer_text", "header_type", "header_image")
    def _onchange_local_preview(self):
        for rec in self:
            rec.preview_body_text = rec.body or ""
            rec.preview_footer_text = rec.footer_text or ""
            rec.preview_header_text = rec.header_text if rec.header_type == "text" else False
            if rec.header_type == "image" and rec.header_image:
                rec.preview_header_image = rec.header_image
            elif rec.source == "odoo" and rec.header_type != "image":
                rec.preview_header_image = False

    @api.constrains("api_name")
    def _check_api_name(self):
        for rec in self:
            if rec.api_name and not re.fullmatch(r"[a-z0-9_]+", rec.api_name):
                raise ValidationError("Template API Name may only contain lowercase letters, numbers and underscores.")

    def _api_context(self):
        self.ensure_one()
        if not self.workspace_id or not self.workspace_id.organization_id:
            raise UserError("Select a Bird workspace first.")
        org = self.workspace_id.organization_id
        if not org.access_key:
            raise UserError("The linked Organization has no Bird Access Key.")
        workspace_uid = self.workspace_id.workspace_id or org.workspace_id
        if not workspace_uid:
            raise UserError("The Bird Workspace ID is missing.")
        return org.access_key, workspace_uid

    def _ensure_channel_group(self):
        self.ensure_one()
        if self.channel_group_id:
            return self.channel_group_id
        access_key, workspace_uid = self._api_context()
        result = self.env["bird.api.service"].get(
            f"/workspaces/{workspace_uid}/channel-groups", access_key
        )
        if not result["ok"]:
            raise UserError("Could not retrieve Bird WhatsApp channel groups: %s" % (result["error"] or "Unknown error"))
        data = result.get("data") or {}
        groups = data if isinstance(data, list) else (data.get("results") or data.get("items") or [])
        selected = False
        for group in groups:
            channels = group.get("channelIds") or []
            if self.channel_id and self.channel_id.channel_id in channels:
                selected = group
                break
        if not selected:
            for group in groups:
                platform = str(group.get("platform") or group.get("type") or "").lower()
                if platform == "whatsapp" or "whatsapp" in platform:
                    selected = group
                    break
        if not selected and len(groups) == 1:
            selected = groups[0]
        group_id = selected and (selected.get("id") or selected.get("channelGroupId"))
        if not group_id:
            raise UserError("No WhatsApp Channel Group was found in Bird for this workspace.")
        self.channel_group_id = group_id
        return group_id

    def _build_platform_content(self):
        self.ensure_one()
        blocks = []
        if self.header_type == "text" and self.header_text:
            blocks.append({"type": "text", "role": "header", "text": {"text": self.header_text}})
        elif self.header_type == "image":
            if not self.header_media_url:
                raise UserError("For an Image Header, enter a public Header Media URL before submitting for approval.")
            blocks.append({"type": "image", "role": "header", "image": {"mediaUrl": self.header_media_url}})
        blocks.append({"type": "text", "role": "body", "text": {"text": self.body or ""}})
        if self.footer_text:
            blocks.append({"type": "text", "role": "footer", "text": {"text": self.footer_text}})
        # Keep button representation intentionally simple and Bird-native.
        actions = []
        for btn in self.button_ids.sorted("sequence"):
            if btn.button_type == "url":
                actions.append({"type": "url", "text": btn.text, "url": btn.website_url})
            elif btn.button_type == "phone":
                actions.append({"type": "call", "text": btn.text, "phoneNumber": btn.phone_number})
            elif btn.button_type == "quick_reply":
                actions.append({"type": "quick-reply", "text": btn.text})
        if actions:
            blocks.append({"type": "actions", "role": "actions", "actions": actions})
        return [{"platform": "whatsapp", "blocks": blocks}]

    def _build_create_payload(self, channel_group_id):
        self.ensure_one()
        return {
            "name": self.name,
            "description": self.description or self.name,
            "defaultLocale": self.locale or "en",
            "supportedPlatforms": ["whatsapp"],
            "platformContent": self._build_platform_content(),
            "deployments": [
                {"key": "whatsappTemplateName", "value": self.api_name},
                {"key": "whatsappTemplateCategory", "value": self.category},
                {"key": "channelGroupId", "value": channel_group_id},
            ],
            "variables": [
                {"name": line.name, "sampleValue": line.sample_value or line.name}
                for line in self.variable_line_ids if line.name
            ],
        }

    def action_submit_for_approval(self):
        self.ensure_one()
        if self.status != "draft":
            raise UserError("Only Draft templates can be submitted.")
        if not self.api_name or not self.body:
            raise UserError("Template API Name and Body are required.")
        if not self.channel_id:
            raise UserError("Select the WhatsApp Channel that this template belongs to.")

        access_key, workspace_uid = self._api_context()
        group_id = self._ensure_channel_group()
        service = self.env["bird.api.service"]

        # Bird documents the combined project/channel-template create endpoint.
        payload = self._build_create_payload(group_id)
        result = service.post(
            f"/workspaces/{workspace_uid}/projects/channel-templates/create",
            access_key,
            payload=payload,
        )
        self.approval_details = service.pretty_json({"create_request": payload, "create_response": result.get("data")})
        if not result["ok"]:
            raise UserError("Bird template creation failed (HTTP %s): %s" % (result["status_code"], result["error"]))

        data = result.get("data") or {}
        project = data.get("project") or {}
        channel_template = data.get("channelTemplate") or data.get("template") or {}
        self.project_id = data.get("projectId") or project.get("id") or self.project_id
        self.bird_template_id = data.get("channelTemplateId") or channel_template.get("id") or data.get("id") or self.bird_template_id
        self.version = str(channel_template.get("version") or data.get("version") or self.version or "1")

        if not self.project_id or not self.bird_template_id:
            raise UserError("Bird created the template but did not return the expected project/template IDs. Open Approval Details and send it to us before retrying.")

        activate = service.put(
            f"/workspaces/{workspace_uid}/projects/{self.project_id}/channel-templates/{self.bird_template_id}/activate",
            access_key,
            payload={},
        )
        self.approval_details = service.pretty_json({
            "create_request": payload,
            "create_response": result.get("data"),
            "activate_response": activate.get("data"),
            "activate_error": activate.get("error"),
        })
        if not activate["ok"]:
            raise UserError("Template was created in Bird but activation failed (HTTP %s): %s" % (activate["status_code"], activate["error"]))

        self.write({"status": "pending", "submitted_at": fields.Datetime.now(), "rejection_reason": False})
        self.message_post(body="Template submitted to Bird / Meta for WhatsApp approval.")
        return self.action_refresh_approval_status(show_notification=True)

    def action_refresh_approval_status(self, show_notification=True):
        self.ensure_one()
        if not self.project_id or not self.bird_template_id:
            raise UserError("This template has not been submitted to Bird yet.")
        access_key, workspace_uid = self._api_context()
        result = self.env["bird.api.service"].get(
            f"/workspaces/{workspace_uid}/projects/{self.project_id}/channel-templates/{self.bird_template_id}",
            access_key,
        )
        if not result["ok"]:
            raise UserError("Bird status refresh failed (HTTP %s): %s" % (result["status_code"], result["error"]))
        data = result.get("data") or {}
        bird_status = str(data.get("status") or "").lower()
        approvals = []
        for content in data.get("platformContent") or []:
            approvals.extend(content.get("approvals") or [])
        approval_status = ""
        rejection = ""
        for approval in approvals:
            approval_status = str(approval.get("status") or approval.get("state") or "").lower() or approval_status
            rejection = approval.get("reason") or approval.get("rejectionReason") or rejection
        effective = approval_status or bird_status
        if effective in ("approved", "active"):
            new_status = "active"
        elif effective in ("rejected", "disabled", "inactive") and rejection:
            new_status = "rejected"
        elif effective in ("rejected",):
            new_status = "rejected"
        else:
            new_status = "pending" if self.status != "draft" else "draft"
        preview_vals = self._extract_preview_from_payload(data, access_key)
        vals = {
            "status": new_status,
            "last_status_sync": fields.Datetime.now(),
            "rejection_reason": rejection or False,
            "approval_details": self.env["bird.api.service"].pretty_json(data),
            "platform_info": json.dumps(data.get("platformInfo", {}), ensure_ascii=False, indent=2),
            "platform_content": json.dumps(data.get("platformContent", []), ensure_ascii=False, indent=2),
            "deployments": json.dumps(data.get("deployments", []), ensure_ascii=False, indent=2),
            "variables": json.dumps(data.get("variables", []), ensure_ascii=False, indent=2),
        }
        vals.update(preview_vals)
        self.write(vals)
        if show_notification:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Template Status",
                    "message": "Current status: %s" % dict(self._fields["status"].selection).get(self.status, self.status),
                    "type": "success" if self.status == "active" else ("danger" if self.status == "rejected" else "info"),
                    "sticky": False,
                },
            }
        return True

    def action_reset_to_draft(self):
        for rec in self:
            if rec.status == "pending":
                raise UserError("A Pending Meta review cannot be reset locally. Wait for the approval result or edit by creating a new version later.")
            rec.write({
                "status": "draft",
                "project_id": False,
                "bird_template_id": False,
                "active_resource_id": False,
                "submitted_at": False,
                "last_status_sync": False,
                "rejection_reason": False,
                "approval_details": False,
                "source": "odoo",
            })
        return True

    def action_open_send_message(self):
        self.ensure_one()
        if self.status != "active":
            raise UserError("Only Approved WhatsApp templates can be sent.")
        return super().action_open_send_message()


class BirdTemplateVariable(models.Model):
    _name = "bird.template.variable"
    _description = "Bird Template Variable"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    template_id = fields.Many2one("bird.template", required=True, ondelete="cascade")
    name = fields.Char(string="Name", required=True)
    sample_value = fields.Char(string="Sample Value", required=True)


class BirdTemplateButton(models.Model):
    _name = "bird.template.button"
    _description = "Bird Template Button"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    template_id = fields.Many2one("bird.template", required=True, ondelete="cascade")
    button_type = fields.Selection(
        [("url", "Visit Website"), ("phone", "Call Number"), ("quick_reply", "Quick Reply")],
        default="quick_reply",
        required=True,
    )
    text = fields.Char(string="Button Text", required=True)
    website_url = fields.Char(string="Website URL")
    phone_number = fields.Char(string="Call Number")

    @api.constrains("button_type", "website_url", "phone_number")
    def _check_button_target(self):
        for rec in self:
            if rec.button_type == "url" and not rec.website_url:
                raise ValidationError("Website URL is required for Visit Website buttons.")
            if rec.button_type == "phone" and not rec.phone_number:
                raise ValidationError("Call Number is required for Call Number buttons.")
