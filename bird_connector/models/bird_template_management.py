import base64
import html
import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone

import requests
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class BirdTemplate(models.Model):
    _inherit = "bird.template"

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if "locale" in fields_list and "default_locale" not in self.env.context:
            locale = False
            workspace_id = self.env.context.get("default_workspace_id")
            if workspace_id:
                workspace = self.env["bird.workspace"].browse(workspace_id).exists()
                if workspace and workspace.organization_id:
                    locale = workspace.organization_id.default_locale
            if not locale:
                organization = self.env["bird.organization"].sudo().search([("state", "=", "active")], limit=1)
                locale = organization.default_locale if organization else False
            vals["locale"] = locale or self.env["ir.config_parameter"].sudo().get_param("bird.default_locale", "en")
        return vals

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
        [("none", "None"), ("text", "Text"), ("image", "Image"), ("video", "Video"), ("document", "Document"), ("location", "Location")],
        default="none",
        required=True,
        tracking=True,
    )
    header_image = fields.Binary(string="Header Image", attachment=True)
    header_image_filename = fields.Char(string="Header Image Filename")

    header_video = fields.Binary(string="Header Video", attachment=True)
    header_video_filename = fields.Char(string="Header Video Filename")
    header_document = fields.Binary(string="Header Document", attachment=True)
    header_document_filename = fields.Char(string="Header Document Filename")
    header_location_name = fields.Char(string="Location Name")
    header_location_address = fields.Char(string="Location Address")
    header_location_latitude = fields.Float(string="Latitude", digits=(10, 7))
    header_location_longitude = fields.Float(string="Longitude", digits=(10, 7))
    header_media_kind = fields.Selection([("image", "Image"), ("video", "Video"), ("document", "Document")], string="Uploaded Media Kind", copy=False, readonly=True)
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
    version_ids = fields.One2many("bird.template.version", "template_id", string="Versions", readonly=True)
    version_count = fields.Integer(string="Versions", compute="_compute_version_count")

    @api.depends("version_ids")
    def _compute_version_count(self):
        for rec in self:
            rec.version_count = len(rec.version_ids)

    def _next_body_variable_key(self):
        self.ensure_one()
        keys = [int(x) for x in re.findall(r"\{\{\s*(\d+)\s*\}\}", self.body or "")]
        return str((max(keys) if keys else 0) + 1)

    def action_add_body_variable(self):
        self.ensure_one()
        if self.status != "draft":
            raise UserError("Variables can only be added while the template is Draft.")
        key = self._next_body_variable_key()
        token = "{{%s}}" % key
        body = self.body or ""
        separator = " " if body and not body.endswith((" ", "\n")) else ""
        self.write({"body": body + separator + token})
        if not self.variable_line_ids.filtered(lambda l: l.key == key):
            self.env["bird.template.variable"].create({
                "template_id": self.id,
                "sequence": int(key) * 10,
                "name": "Body - %s" % token,
                "key": key,
                "sample_value": "Sample Value",
                "variable_type": "free_text",
            })
        # Re-open only this form so the server-side body change is visible immediately.
        # This avoids forcing the user to manually refresh the browser.
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": "bird.template",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
            "context": dict(self.env.context, form_view_initial_mode="edit"),
        }

    def _sync_numbered_body_variables(self):
        for rec in self:
            if not rec.id:
                continue
            keys = re.findall(r"\{\{\s*(\d+)\s*\}\}", rec.body or "")
            wanted = []
            for key in keys:
                if key not in wanted:
                    wanted.append(key)
            existing = {line.key: line for line in rec.variable_line_ids if line.key}
            for pos, key in enumerate(wanted, 1):
                if key not in existing:
                    self.env["bird.template.variable"].create({
                        "template_id": rec.id,
                        "sequence": pos * 10,
                        "name": "Body - {{%s}}" % key,
                        "key": key,
                        "sample_value": "Sample Value",
                        "variable_type": "free_text",
                    })
            auto_lines = rec.variable_line_ids.filtered(lambda l: l.key and re.fullmatch(r"\d+", l.key or "") and (l.name or "").startswith("Body - {{"))
            auto_lines.filtered(lambda l: l.key not in wanted).unlink()

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
        records._sync_numbered_body_variables()
        return records

    def write(self, vals):
        vals = dict(vals)
        if any(k in vals for k in ("header_image", "header_video", "header_document")):
            if vals.get("header_image") or vals.get("header_video") or vals.get("header_document"):
                vals.setdefault("header_media_token", uuid.uuid4().hex)
                vals.setdefault("header_media_url", False)
                vals.setdefault("header_media_kind", False)
            elif any(k in vals and not vals.get(k) for k in ("header_image", "header_video", "header_document")):
                vals.setdefault("header_media_url", False)
                vals.setdefault("header_media_kind", False)
        result = super().write(vals)
        preview_sources = {"body", "footer_text", "header_text", "header_type", "header_image", "header_video", "header_document", "header_location_name", "header_location_address", "header_location_latitude", "header_location_longitude"}
        if preview_sources.intersection(vals):
            self._sync_persistent_preview()
        if "body" in vals and not self.env.context.get("skip_bird_variable_sync"):
            self.with_context(skip_bird_variable_sync=True)._sync_numbered_body_variables()
        return result

    def _ensure_header_media_url(self):
        """Upload image/video/document sample media to Bird and return its mediaUrl."""
        self.ensure_one()
        media_map = {
            "image": (self.header_image, self.header_image_filename or f"bird-template-{self.id}.jpg", "image/jpeg"),
            "video": (self.header_video, self.header_video_filename or f"bird-template-{self.id}.mp4", "video/mp4"),
            "document": (self.header_document, self.header_document_filename or f"bird-template-{self.id}.pdf", "application/pdf"),
        }
        if self.header_type not in media_map:
            return False
        binary_value, filename, fallback_type = media_map[self.header_type]
        if self.header_media_url and self.header_media_kind == self.header_type:
            return self.header_media_url
        if not binary_value:
            raise UserError("Upload the %s header file before submitting for approval." % self.header_type.title())

        access_key, workspace_uid = self._api_context()
        service = self.env["bird.api.service"]
        content_type = mimetypes.guess_type(filename)[0] or fallback_type
        presigned = service.post(
            f"/workspaces/{workspace_uid}/channel-media/presigned-upload",
            access_key,
            payload={"contentType": content_type},
        )
        if not presigned.get("ok"):
            raise UserError("Bird could not create a media upload URL (HTTP %s): %s" % (presigned.get("status_code"), presigned.get("error") or presigned.get("data") or "Unknown error"))
        data = presigned.get("data") or {}
        media_url, upload_url = data.get("mediaUrl"), data.get("uploadUrl")
        upload_method = str(data.get("uploadMethod") or "POST").upper()
        form_data = data.get("uploadFormData") or {}
        if not media_url or not upload_url:
            raise UserError("Bird media upload response did not contain mediaUrl/uploadUrl.")
        try:
            binary = base64.b64decode(binary_value)
            if upload_method == "POST":
                upload_response = requests.post(upload_url, data=form_data, files={"file": (filename, binary, content_type)}, timeout=90)
            else:
                upload_response = requests.request(upload_method, upload_url, data=binary, headers={"Content-Type": content_type}, timeout=90)
        except Exception as exc:
            raise UserError("Uploading the Header %s to Bird failed: %s" % (self.header_type.title(), exc))
        if upload_response.status_code not in (200, 201, 202, 204):
            raise UserError("Uploading the Header %s to Bird failed (HTTP %s): %s" % (self.header_type.title(), upload_response.status_code, upload_response.text[:1000]))
        super(BirdTemplate, self).write({"header_media_url": media_url, "header_media_kind": self.header_type})
        return media_url

    @api.depends(
        "preview_header_image", "preview_header_text", "preview_body_text",
        "preview_footer_text", "preview_button_1", "preview_button_1_type",
        "preview_button_2", "preview_button_2_type", "preview_button_3",
        "preview_button_3_type", "header_image", "header_type", "header_text",
        "body", "footer_text", "locale", "button_ids.text", "button_ids.button_type",
        "button_ids.sequence", "header_video", "header_video_filename", "header_document", "header_document_filename",
        "header_location_name", "header_location_address", "header_location_latitude", "header_location_longitude",
    )
    def _compute_preview_html(self):
        # Structure intentionally mirrors Bird's 320px WhatsApp preview: green
        # brand header, 520px chat area, white message bubble and action rows.
        icon_map = {"url": "🌐", "phone": "☎", "quick_reply": ""}
        for rec in self:
            body = rec.body or rec.preview_body_text or ""
            footer = rec.footer_text or rec.preview_footer_text or ""
            header_text = rec.header_text if rec.header_type == "text" else (rec.preview_header_text or "")
            image_data = rec.header_image if rec.header_type == "image" and rec.header_image else rec.preview_header_image

            image_html = ""
            if image_data:
                # Odoo's HTML field/browser CSP can block or rewrite large data: URLs.
                # For persisted records use /web/image, which is reliable in the backend
                # and automatically benefits from Odoo's image response handling.
                if rec.id and rec.header_image:
                    cache_key = fields.Datetime.to_string(rec.write_date or fields.Datetime.now()).replace(" ", "T")
                    image_src = "/web/image/bird.template/%s/header_image?unique=%s" % (rec.id, cache_key)
                else:
                    image_b64 = image_data.decode("ascii") if isinstance(image_data, bytes) else str(image_data)
                    mime = mimetypes.guess_type(rec.header_image_filename or "image.jpg")[0] or "image/jpeg"
                    image_src = "data:%s;base64,%s" % (mime, image_b64)
                image_html = (
                    '<div style="padding:4px 4px 0 4px;line-height:0;">'
                    f'<img src="{html.escape(image_src, quote=True)}" style="display:block;width:100%;height:auto;max-height:285px;object-fit:cover;border-radius:6px;"/>'
                    '</div>'
                )

            if rec.header_type == "video" and rec.header_video:
                image_html = ('<div style="margin:4px;border-radius:6px;background:#111;color:#fff;height:150px;display:flex;align-items:center;justify-content:center;font-size:14px;">▶ Video: %s</div>' % html.escape(rec.header_video_filename or "video"))
            elif rec.header_type == "document" and rec.header_document:
                image_html = ('<div style="margin:4px;padding:16px;border-radius:6px;background:#f5f6f7;border:1px solid #e5e7eb;color:#43556C;font-size:13px;display:flex;align-items:center;gap:8px;">📄 <span>%s</span></div>' % html.escape(rec.header_document_filename or "Document"))
            elif rec.header_type == "location":
                loc = rec.header_location_name or "Location"
                address = rec.header_location_address or ""
                image_html = ('<div style="margin:4px;border-radius:6px;overflow:hidden;border:1px solid #e5e7eb;"><div style="height:105px;background:#dfe7e3;display:flex;align-items:center;justify-content:center;font-size:32px;">📍</div><div style="padding:8px;font-size:12px;color:#262628;"><b>%s</b><br/>%s</div></div>' % (html.escape(loc), html.escape(address)))

            local_buttons = rec.button_ids.sorted("sequence")[:3]
            buttons = [(b.text or "", b.button_type or "quick_reply") for b in local_buttons]
            if not buttons:
                for idx in range(1, 4):
                    label = getattr(rec, f"preview_button_{idx}")
                    btype = getattr(rec, f"preview_button_{idx}_type") or "quick_reply"
                    if label:
                        buttons.append((label, btype))

            direction = "rtl" if (rec.locale or "").lower().startswith("ar") else "ltr"
            text_align = "right" if direction == "rtl" else "left"
            header_html = (
                f'<div style="padding:4px;font-weight:700;font-size:14px;color:#262628;white-space:pre-wrap;overflow-wrap:anywhere;">{html.escape(header_text)}</div>'
                if header_text else ""
            )
            body_html = html.escape(body).replace("\n", "<br/>")
            footer_html = (
                f'<div style="padding:4px;color:#43556C;font-size:12px;font-weight:300;white-space:pre-wrap;overflow-wrap:anywhere;">{html.escape(footer)}</div>'
                if footer else ""
            )
            rows=[]
            for label,btype in buttons:
                icon=icon_map.get(btype, "")
                icon_html=f'<span style="margin-right:6px;font-size:15px;">{icon}</span>' if icon else ""
                rows.append(
                    '<div style="border-top:1px solid #eef0f2;padding:0 4px;background:#fff;">'
                    '<div style="height:40px;display:flex;align-items:center;justify-content:center;color:#8484FF;font-size:14px;font-weight:500;text-align:center;">'
                    + icon_html + f'<span>{html.escape(label)}</span></div></div>'
                )
            buttons_html="".join(rows)

            rec.preview_html = (
                '<div style="width:352px!important;min-width:352px!important;max-width:352px!important;margin:0 auto;box-sizing:border-box;">'
                '<div style="position:relative;width:320px!important;min-width:320px!important;margin:0 auto;">'
                '<div style="height:52px;display:flex;align-items:center;gap:8px;border-radius:9px 9px 0 0;background:#085B53;padding:0 12px;box-sizing:border-box;">'
                '<div style="width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:50%;border:1px solid #f3f4f6;background:#fff;color:#2d7fd3;font-weight:800;font-size:14px;">B</div>'
                '<span style="font-size:16px;line-height:24px;font-weight:700;color:#fff;">Bird</span></div>'
                '<div style="min-height:520px;border-radius:0 0 9px 9px;padding:12px;box-sizing:border-box;background-color:#efeae2;'
                'background-image:radial-gradient(rgba(120,110,95,.08) 1px,transparent 1px);background-size:18px 18px;">'
                '<div style="overflow:hidden;border-radius:8px 8px 8px 0;background:#fff;box-shadow:0 1px 1px rgba(0,0,0,.04);">'
                + image_html + '<div style="display:flex;flex-direction:column;">' + header_html
                + f'<div dir="{direction}" style="padding:4px;font-size:14px;line-height:20px;color:#262628;text-align:{text_align};white-space:pre-wrap;overflow-wrap:anywhere;">{body_html}</div>'
                + footer_html + buttons_html + '</div></div></div></div></div>'
            )

    @api.onchange("body", "header_text", "footer_text", "header_type", "header_image", "header_video", "header_document", "header_location_name", "header_location_address", "header_location_latitude", "header_location_longitude")
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
            blocks.append({"type": "image", "role": "header", "image": {"mediaUrl": media_url, "altText": self.name or ""}})
        elif self.header_type == "video":
            media_url = self._ensure_header_media_url()
            blocks.append({"type": "video", "role": "header", "video": {"mediaUrl": media_url}})
        elif self.header_type == "document":
            media_url = self._ensure_header_media_url()
            blocks.append({"type": "file", "role": "header", "file": {"mediaUrl": media_url, "filename": self.header_document_filename or "document.pdf"}})
        elif self.header_type == "location":
            raise UserError("Bird's WhatsApp approved-template documentation does not expose Location as a template header. Location is kept in the Odoo UI/preview for parity, but cannot be submitted as an approved template header. Use None/Text/Image/Video/Document for submission.")

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
                    "key": line.key or line._get_variable_key(),
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

    def action_sync_versions(self):
        self.ensure_one()
        if not self.project_id:
            raise UserError("This template has no Bird Project ID yet.")
        access_key, workspace_uid = self._api_context()
        service = self.env["bird.api.service"]
        result = service.get(f"/workspaces/{workspace_uid}/projects/{self.project_id}/channel-templates", access_key)
        if not result.get("ok"):
            raise UserError("Could not retrieve template versions from Bird (HTTP %s): %s" % (result.get("status_code"), result.get("error") or result.get("data")))
        data = result.get("data") or {}
        items = data if isinstance(data, list) else (data.get("results") or data.get("items") or data.get("channelTemplates") or data.get("resources") or [])
        Version = self.env["bird.template.version"].sudo()
        seen = []
        for item in items:
            if not isinstance(item, dict):
                continue
            vid = item.get("id") or item.get("channelTemplateId") or item.get("resourceId") or item.get("versionId")
            if not vid:
                continue
            seen.append(vid)
            status = str(item.get("status") or item.get("state") or "draft").lower()
            approvals=[]
            for content in item.get("platformContent") or []:
                approvals += content.get("approvals") or []
            approval_status = next((str(a.get("status") or "").lower() for a in approvals if a.get("status")), "")
            if approval_status:
                status = approval_status
            raw_dt = item.get("updatedAt") or item.get("lastUpdated") or item.get("modifiedAt")
            parsed_dt = False
            if raw_dt:
                try:
                    parsed_dt = datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00"))
                    if parsed_dt.tzinfo:
                        parsed_dt = parsed_dt.astimezone(timezone.utc).replace(tzinfo=None)
                except Exception:
                    parsed_dt = False
            vals = {
                "template_id": self.id,
                "bird_version_id": vid,
                "description": item.get("description") or item.get("name") or self.name,
                "status": status if status in ("draft","pending","active","approved","inactive","rejected") else "draft",
                "publisher": item.get("publisherName") or item.get("publishedBy") or item.get("createdBy") or "",
                "last_updated": parsed_dt,
                "last_updated_by": item.get("updatedByName") or item.get("lastUpdatedBy") or item.get("updatedBy") or "",
                "is_current": bool(status in ("active", "approved") or vid == self.bird_template_id or vid == self.active_resource_id),
                "raw_json": service.pretty_json(item),
            }
            existing = Version.search([("template_id","=",self.id),("bird_version_id","=",vid)], limit=1)
            if existing: existing.write(vals)
            else: Version.create(vals)
        if seen:
            Version.search([("template_id","=",self.id),("bird_version_id","not in",seen)]).unlink()
        return True

    def action_open_versions(self):
        self.ensure_one()
        self.action_sync_versions()
        return {
            "type": "ir.actions.act_window",
            "name": "Template Versions",
            "res_model": "bird.template.version",
            "view_mode": "list,form",
            "domain": [("template_id", "=", self.id)],
            "context": {"default_template_id": self.id, "create": False},
        }

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


    @api.model
    def _cleanup_duplicate_projects(self):
        """Merge historical duplicate template rows created from Bird versions.

        A canonical template is selected per (workspace, project_id), preferring
        Approved/Active, then Pending, then Draft, then Rejected. Message logs
        and version rows are preserved and reassigned before duplicate records
        are removed. Local drafts without a Bird Project ID are never touched.
        """
        Template = self.sudo()
        domain = [("project_id", "!=", False)]
        records = Template.search(domain, order="workspace_id, project_id, id")
        grouped = {}
        for rec in records:
            key = (rec.workspace_id.id, rec.project_id)
            grouped.setdefault(key, Template.browse())
            grouped[key] |= rec

        rank = {"active": 50, "pending": 40, "draft": 30, "rejected": 20}
        groups_merged = 0
        removed = 0
        Version = self.env["bird.template.version"].sudo()
        Message = self.env["bird.message.log"].sudo()

        for _key, group in grouped.items():
            if len(group) <= 1:
                continue
            canonical = sorted(group, key=lambda r: (rank.get(r.status, 0), r.id), reverse=True)[0]
            duplicates = group - canonical
            groups_merged += 1

            for dup in duplicates:
                # Preserve every known Bird version without creating duplicate
                # version rows under the canonical template.
                for version in dup.version_ids:
                    existing = Version.search([
                        ("template_id", "=", canonical.id),
                        ("bird_version_id", "=", version.bird_version_id),
                    ], limit=1)
                    if existing:
                        # Keep the richer/current information then remove the duplicate row.
                        vals = {}
                        if version.is_current and not existing.is_current:
                            vals["is_current"] = True
                        if version.last_updated and (not existing.last_updated or version.last_updated > existing.last_updated):
                            vals.update({
                                "description": version.description,
                                "status": version.status,
                                "publisher": version.publisher,
                                "last_updated": version.last_updated,
                                "last_updated_by": version.last_updated_by,
                                "raw_json": version.raw_json,
                            })
                        if vals:
                            existing.write(vals)
                        version.unlink()
                    else:
                        version.write({"template_id": canonical.id})

                # Preserve message history.
                Message.search([("template_id", "=", dup.id)]).write({"template_id": canonical.id})
                removed += 1
                dup.unlink()

            # Ensure only one version is flagged current whenever possible.
            current_versions = canonical.version_ids.filtered("is_current")
            if len(current_versions) > 1:
                preferred = current_versions.filtered(lambda v: v.bird_version_id == canonical.bird_template_id)[:1] or current_versions[:1]
                (current_versions - preferred).write({"is_current": False})

        return {"groups": groups_merged, "removed": removed}



class BirdTemplateVersion(models.Model):
    _name = "bird.template.version"
    _description = "Bird Template Version"
    _order = "is_current desc, last_updated desc, id desc"

    template_id = fields.Many2one("bird.template", required=True, ondelete="cascade", index=True)
    bird_version_id = fields.Char(string="Version ID", required=True, index=True)
    description = fields.Char(string="Description")
    status = fields.Selection([
        ("draft", "Draft"), ("pending", "Pending"), ("active", "Active"), ("approved", "Approved"),
        ("inactive", "Inactive"), ("rejected", "Rejected"),
    ], default="draft", required=True)
    publisher = fields.Char(string="Publisher")
    last_updated = fields.Datetime(string="Last Updated")
    last_updated_by = fields.Char(string="Last Updated By")
    is_current = fields.Boolean(string="Current / Active")
    raw_json = fields.Text(string="Raw Bird Response", readonly=True)

    _sql_constraints = [("bird_template_version_uniq", "unique(template_id, bird_version_id)", "This Bird template version already exists.")]


class BirdTemplateVariable(models.Model):
    _name = "bird.template.variable"
    _description = "Bird Template Variable"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    template_id = fields.Many2one("bird.template", required=True, ondelete="cascade")
    name = fields.Char(string="Name", required=True)
    key = fields.Char(string="Variable Key", help="The value used inside {{key}} in Bird.")
    sample_value = fields.Char(string="Sample Value", required=True, default="Sample Value")
    variable_type = fields.Selection([
        ("user_name", "User Name"),
        ("user_mobile", "User Mobile"),
        ("free_text", "Free Text"),
        ("portal_link", "Portal Link"),
        ("field", "Field of Model"),
    ], string="Type", default="free_text", required=True)
    model_id = fields.Many2one("ir.model", string="Model", ondelete="set null")
    field_id = fields.Many2one("ir.model.fields", string="Field", ondelete="set null", domain="[('model_id', '=', model_id)]")

    def _get_variable_key(self):
        self.ensure_one()
        if self.key:
            return self.key
        match = re.search(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", self.name or "")
        return match.group(1) if match else (self.name or "").strip()

    @api.onchange("name")
    def _onchange_name_key(self):
        for rec in self:
            if not rec.key and rec.name:
                rec.key = rec._get_variable_key()

    @api.onchange("variable_type")
    def _onchange_variable_type(self):
        for rec in self:
            if rec.variable_type != "field":
                rec.model_id = False
                rec.field_id = False


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
