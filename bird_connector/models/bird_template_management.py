import base64
import html
import json
import mimetypes
import re
import uuid

import requests
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
    header_media_token = fields.Char(string="Header Media Token", copy=False, readonly=True)
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
    preview_html = fields.Html(string="WhatsApp Preview", compute="_compute_preview_html", sanitize=False)

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


    def _persistent_preview_vals(self):
        self.ensure_one()
        buttons = self.button_ids.sorted("sequence")[:3]
        vals = {
            "preview_body_text": self.body or "",
            "preview_footer_text": self.footer_text or False,
            "preview_header_text": self.header_text if self.header_type == "text" else False,
            "preview_header_image": self.header_image if self.header_type == "image" and self.header_image else False,
        }
        for idx in range(1, 4):
            button = buttons[idx - 1] if len(buttons) >= idx else False
            vals[f"preview_button_{idx}"] = button.text if button else False
            vals[f"preview_button_{idx}_type"] = button.button_type if button else False
        return vals

    def _sync_persistent_preview(self):
        for rec in self:
            vals = rec._persistent_preview_vals()
            # Bypass this model override to avoid recursive writes.
            super(BirdTemplate, rec).write(vals)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("header_image") and not vals.get("header_media_token"):
                vals["header_media_token"] = uuid.uuid4().hex
        records = super().create(vals_list)
        records._sync_persistent_preview()
        return records

    def write(self, vals):
        vals = dict(vals)
        if "header_image" in vals:
            if vals.get("header_image"):
                vals.setdefault("header_media_token", uuid.uuid4().hex)
                vals.setdefault("header_media_url", False)
            else:
                vals.setdefault("header_media_token", False)
                vals.setdefault("header_media_url", False)
        result = super().write(vals)
        preview_sources = {"body", "footer_text", "header_text", "header_type", "header_image"}
        if preview_sources.intersection(vals):
            self._sync_persistent_preview()
        return result

    def _ensure_header_media_url(self):
        """Upload the image to Bird Channel Media and return Bird's media URL."""
        self.ensure_one()
        if self.header_type != "image":
            return False
        if self.header_media_url and "bird.com" in self.header_media_url:
            return self.header_media_url
        if not self.header_image:
            raise UserError("Upload a Header Image before submitting for approval.")

        access_key, workspace_uid = self._api_context()
        service = self.env["bird.api.service"]
        filename = self.header_image_filename or f"bird-template-{self.id}.jpg"
        content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"

        presigned = service.post(
            f"/workspaces/{workspace_uid}/channel-media/presigned-upload",
            access_key,
            payload={"contentType": content_type},
        )
        if not presigned.get("ok"):
            raise UserError(
                "Bird could not create a media upload URL (HTTP %s): %s"
                % (presigned.get("status_code"), presigned.get("error") or presigned.get("data") or "Unknown error")
            )

        data = presigned.get("data") or {}
        media_url = data.get("mediaUrl")
        upload_url = data.get("uploadUrl")
        upload_method = str(data.get("uploadMethod") or "POST").upper()
        form_data = data.get("uploadFormData") or {}
        if not media_url or not upload_url:
            raise UserError("Bird media upload response did not contain mediaUrl/uploadUrl.")

        try:
            binary = base64.b64decode(self.header_image)
        except Exception as exc:
            raise UserError("Could not decode the Header Image: %s" % exc)

        try:
            if upload_method == "POST":
                upload_response = requests.post(
                    upload_url,
                    data=form_data,
                    files={"file": (filename, binary, content_type)},
                    timeout=60,
                )
            else:
                upload_response = requests.request(
                    upload_method,
                    upload_url,
                    data=binary,
                    headers={"Content-Type": content_type},
                    timeout=60,
                )
        except Exception as exc:
            raise UserError("Uploading the Header Image to Bird failed: %s" % exc)

        if upload_response.status_code not in (200, 201, 202, 204):
            raise UserError(
                "Uploading the Header Image to Bird failed (HTTP %s): %s"
                % (upload_response.status_code, upload_response.text[:1000])
            )

        super(BirdTemplate, self).write({"header_media_url": media_url})
        return media_url

    @api.depends(
        "preview_header_image", "preview_header_text", "preview_body_text",
        "preview_footer_text", "preview_button_1", "preview_button_1_type",
        "preview_button_2", "preview_button_2_type", "preview_button_3",
        "preview_button_3_type", "header_image", "header_type", "header_text",
        "body", "footer_text", "locale", "button_ids.text", "button_ids.button_type",
        "button_ids.sequence",
    )
    def _compute_preview_html(self):
        icon_map = {"url": "↗", "phone": "☎", "quick_reply": "↩"}
        for rec in self:
            body = rec.body or rec.preview_body_text or ""
            footer = rec.footer_text or rec.preview_footer_text or ""
            header_text = rec.header_text if rec.header_type == "text" else (rec.preview_header_text or "")
            image_data = rec.header_image if rec.header_type == "image" and rec.header_image else rec.preview_header_image

            image_html = ""
            if image_data:
                image_b64 = image_data.decode("ascii") if isinstance(image_data, bytes) else str(image_data)
                mime = mimetypes.guess_type(rec.header_image_filename or "image.jpg")[0] or "image/jpeg"
                image_html = (
                    '<div style="width:100%;line-height:0;">'
                    f'<img src="data:{mime};base64,{image_b64}" style="display:block;width:100%;height:auto;max-height:320px;object-fit:cover;"/>'
                    '</div>'
                )

            buttons = []
            local_buttons = rec.button_ids.sorted("sequence")[:3]
            if local_buttons:
                buttons = [(b.text or "", b.button_type or "quick_reply") for b in local_buttons]
            else:
                for idx in range(1, 4):
                    label = getattr(rec, f"preview_button_{idx}")
                    btype = getattr(rec, f"preview_button_{idx}_type") or "quick_reply"
                    if label:
                        buttons.append((label, btype))

            direction = "rtl" if (rec.locale or "").lower().startswith("ar") else "ltr"
            text_align = "right" if direction == "rtl" else "left"
            header_html = ""
            if header_text:
                header_html = f'<div style="font-weight:700;font-size:15px;margin-bottom:7px;">{html.escape(header_text)}</div>'
            body_html = html.escape(body).replace("\n", "<br/>")
            footer_html = f'<div style="color:#667781;font-size:11.5px;margin-top:8px;">{html.escape(footer)}</div>' if footer else ""

            rows = []
            for label, btype in buttons:
                rows.append(
                    '<div style="height:44px;display:flex;align-items:center;justify-content:center;gap:7px;color:#0067ff;font-size:14px;border-top:1px solid #e9edef;background:#fff;">'
                    f'<span style="font-size:16px;">{icon_map.get(btype, "↩")}</span><span>{html.escape(label)}</span></div>'
                )
            buttons_html = "".join(rows)

            rec.preview_html = (
                '<div style="display:flex;justify-content:center;width:100%;padding:8px 0 18px;box-sizing:border-box;">'
                '<div style="width:352px;min-height:576px;background:#efeae2;border-radius:12px;padding:18px 12px;box-sizing:border-box;box-shadow:0 1px 2px rgba(0,0,0,.12);">'
                '<div style="width:100%;background:#006257;color:white;height:48px;border-radius:9px 9px 0 0;display:flex;align-items:center;padding:0 14px;box-sizing:border-box;font-weight:700;gap:9px;">'
                '<span style="width:25px;height:25px;border-radius:50%;background:#fff;color:#0a7c70;display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;">B</span><span>Bird</span></div>'
                '<div style="background:#fff;border-radius:0 0 8px 8px;overflow:hidden;">'
                + image_html +
                f'<div dir="{direction}" style="padding:11px 13px 12px;text-align:{text_align};font-size:13.5px;line-height:1.45;color:#111b21;min-height:55px;box-sizing:border-box;">'
                + header_html + f'<div>{body_html}</div>' + footer_html + '</div>' + buttons_html + '</div></div></div>'
            )

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

    def _build_project_payload(self):
        self.ensure_one()
        # Bird Touchpoints Projects API requires a project type.
        # Locale/platform settings belong to the channel-template payload, not
        # to the Project creation request. Keep this payload minimal.
        return {
            "name": self.name,
            "description": self.description or self.name,
            "type": "channelTemplate",
            "scope": 0,
        }

    def _build_platform_content(self, channel_group_id):
        self.ensure_one()
        blocks = []
        if self.header_type == "text" and self.header_text:
            blocks.append({"type": "text", "role": "header", "text": {"text": self.header_text}})
        elif self.header_type == "image":
            media_url = self._ensure_header_media_url()
            blocks.append({
                "type": "image",
                "role": "header",
                "image": {"mediaUrl": media_url, "altText": self.name or ""},
            })

        blocks.append({"type": "text", "role": "body", "text": {"text": self.body or ""}})

        if self.footer_text:
            blocks.append({"type": "text", "role": "footer", "text": {"text": self.footer_text}})

        # Bird WhatsApp template buttons are separate blocks, not a single
        # {type: actions, actions: [...]} container. Bird also requires mixed
        # button types to be ordered: link-action -> call-phone-number-action
        # -> reply-action. Keep the user's sequence within each button type.
        buttons = self.button_ids.sorted("sequence")
        ordered_buttons = (
            buttons.filtered(lambda b: b.button_type == "url")
            | buttons.filtered(lambda b: b.button_type == "phone")
            | buttons.filtered(lambda b: b.button_type == "quick_reply")
        )

        for btn in ordered_buttons:
            if btn.button_type == "url":
                blocks.append({
                    "type": "link-action",
                    "linkAction": {
                        "text": btn.text,
                        "url": btn.website_url,
                    },
                })
            elif btn.button_type == "phone":
                blocks.append({
                    "type": "call-phone-number-action",
                    "callPhoneNumberAction": {
                        "text": btn.text,
                        "phoneNumber": btn.phone_number,
                    },
                })
            elif btn.button_type == "quick_reply":
                blocks.append({
                    "type": "reply-action",
                    "replyAction": {
                        "text": btn.text,
                        "payload": btn.text,
                    },
                })

        return [{
            "locale": self.locale or "en",
            "type": "text",
            "platform": "whatsapp",
            "channelGroupIds": [channel_group_id],
            "blocks": blocks,
        }]

    def _build_channel_template_payload(self, channel_group_id):
        self.ensure_one()
        return {
            "name": self.name,
            "description": self.description or self.name,
            "defaultLocale": self.locale or "en",
            "supportedPlatforms": ["whatsapp"],
            "platformContent": self._build_platform_content(channel_group_id),
            "deployments": [
                {
                    "key": "whatsappTemplateName",
                    "platform": "whatsapp",
                    "value": self.api_name,
                },
                {
                    "key": "whatsappCategory",
                    "platform": "whatsapp",
                    "value": self.category,
                },
                {
                    "key": "whatsappAllowCategoryChange",
                    "platform": "whatsapp",
                    "value": "true",
                },
            ],
            "variables": [
                {
                    "type": "string",
                    "key": line.name,
                    "examplesLocale": {
                        (self.locale or "en"): {
                            "exampleValueStrings": [line.sample_value or line.name]
                        }
                    },
                }
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

        # Bird Support confirmed that template creation is a staged Touchpoints flow:
        # 1) create the Project, 2) create a Channel Template under that Project,
        # 3) activate the Channel Template to submit it for Meta approval.
        audit = {"workspace_id": workspace_uid, "channel_group_id": group_id}

        if not self.project_id:
            project_payload = self._build_project_payload()
            project_result = service.post(
                f"/workspaces/{workspace_uid}/projects",
                access_key,
                payload=project_payload,
            )
            audit.update({
                "project_create_request": project_payload,
                "project_create_status": project_result.get("status_code"),
                "project_create_response": project_result.get("data"),
                "project_create_error": project_result.get("error"),
            })
            self.approval_details = service.pretty_json(audit)
            if not project_result["ok"]:
                response_payload = project_result.get("data") or project_result.get("error") or "Unknown error"
                raise UserError(
                    "Bird Project creation failed.\n\n"
                    "HTTP Status: %s\n"
                    "Endpoint: POST /workspaces/{workspaceId}/projects\n\n"
                    "Request Payload:\n%s\n\n"
                    "Bird Response:\n%s"
                    % (
                        project_result.get("status_code"),
                        json.dumps(project_payload, ensure_ascii=False, indent=2),
                        json.dumps(response_payload, ensure_ascii=False, indent=2)
                        if not isinstance(response_payload, str) else response_payload,
                    )
                )

            project_data = project_result.get("data") or {}
            project_obj = project_data.get("project") if isinstance(project_data, dict) else {}
            project_id = (
                (project_data.get("id") if isinstance(project_data, dict) else False)
                or (project_data.get("projectId") if isinstance(project_data, dict) else False)
                or ((project_obj or {}).get("id") if isinstance(project_obj, dict) else False)
            )
            if not project_id:
                self.approval_details = service.pretty_json(audit)
                raise UserError(
                    "Bird created the Project but the response did not contain a Project ID. "
                    "Open Approval Details and send us the response before retrying."
                )
            self.project_id = project_id

        template_payload = self._build_channel_template_payload(group_id)
        template_result = service.post(
            f"/workspaces/{workspace_uid}/projects/{self.project_id}/channel-templates",
            access_key,
            payload=template_payload,
        )
        audit.update({
            "project_id": self.project_id,
            "channel_template_create_request": template_payload,
            "channel_template_create_status": template_result.get("status_code"),
            "channel_template_create_response": template_result.get("data"),
            "channel_template_create_error": template_result.get("error"),
        })
        self.approval_details = service.pretty_json(audit)
        if not template_result["ok"]:
            response_payload = template_result.get("data") or template_result.get("error") or "Unknown error"
            raise UserError(
                "Bird Channel Template creation failed.\n\n"
                "HTTP Status: %s\n"
                "Endpoint: POST /workspaces/{workspaceId}/projects/{projectId}/channel-templates\n\n"
                "Request Payload:\n%s\n\n"
                "Bird Response:\n%s"
                % (
                    template_result.get("status_code"),
                    json.dumps(template_payload, ensure_ascii=False, indent=2),
                    json.dumps(response_payload, ensure_ascii=False, indent=2)
                    if not isinstance(response_payload, str) else response_payload,
                )
            )

        template_data = template_result.get("data") or {}
        template_obj = template_data.get("channelTemplate") if isinstance(template_data, dict) else {}
        self.bird_template_id = (
            (template_data.get("id") if isinstance(template_data, dict) else False)
            or (template_data.get("channelTemplateId") if isinstance(template_data, dict) else False)
            or ((template_obj or {}).get("id") if isinstance(template_obj, dict) else False)
            or self.bird_template_id
        )
        self.version = str(
            ((template_obj or {}).get("version") if isinstance(template_obj, dict) else False)
            or (template_data.get("version") if isinstance(template_data, dict) else False)
            or self.version
            or "1"
        )

        if not self.bird_template_id:
            self.approval_details = service.pretty_json(audit)
            raise UserError(
                "Bird created the Channel Template but the response did not contain a Channel Template ID. "
                "Open Approval Details and send us the response before retrying."
            )

        activate = service.put(
            f"/workspaces/{workspace_uid}/projects/{self.project_id}/channel-templates/{self.bird_template_id}/activate",
            access_key,
            payload={},
        )
        audit.update({
            "channel_template_id": self.bird_template_id,
            "activate_status": activate.get("status_code"),
            "activate_response": activate.get("data"),
            "activate_error": activate.get("error"),
        })
        self.approval_details = service.pretty_json(audit)
        if not activate["ok"]:
            raise UserError(
                "The Project and Channel Template were created in Bird, but activation/submission failed "
                "(HTTP %s): %s\n\nOpen Approval Details for the exact Bird response."
                % (activate["status_code"], activate["error"] or "Unknown error")
            )

        self.write({
            "status": "pending",
            "submitted_at": fields.Datetime.now(),
            "rejection_reason": False,
            "source": "odoo",
        })
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

        # Bird may omit action/button blocks from some status/detail responses.
        # Never erase the locally configured preview buttons in that case.
        local_preview = self._persistent_preview_vals()
        if not any(preview_vals.get(f"preview_button_{idx}") for idx in range(1, 4)):
            for idx in range(1, 4):
                preview_vals[f"preview_button_{idx}"] = local_preview.get(f"preview_button_{idx}")
                preview_vals[f"preview_button_{idx}_type"] = local_preview.get(f"preview_button_{idx}_type")

        # The same defensive fallback keeps locally-entered content visible when
        # Bird returns a partial payload while an approval/status is refreshed.
        for key in ("preview_body_text", "preview_footer_text", "preview_header_text", "preview_header_image"):
            if not preview_vals.get(key) and local_preview.get(key):
                preview_vals[key] = local_preview[key]

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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("template_id")._sync_persistent_preview()
        return records

    def write(self, vals):
        templates_before = self.mapped("template_id")
        result = super().write(vals)
        (templates_before | self.mapped("template_id"))._sync_persistent_preview()
        return result

    def unlink(self):
        templates = self.mapped("template_id")
        result = super().unlink()
        templates.exists()._sync_persistent_preview()
        return result

    @api.constrains("button_type", "website_url", "phone_number")
    def _check_button_target(self):
        for rec in self:
            if rec.button_type == "url" and not rec.website_url:
                raise ValidationError("Website URL is required for Visit Website buttons.")
            if rec.button_type == "phone" and not rec.phone_number:
                raise ValidationError("Call Number is required for Call Number buttons.")
