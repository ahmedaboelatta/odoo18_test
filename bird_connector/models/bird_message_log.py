import json

from markupsafe import Markup, escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BirdMessageLog(models.Model):
    _name = "bird.message.log"
    _description = "Bird Message Log"
    _order = "create_date desc, id desc"

    channel_id = fields.Many2one("bird.channel", string="Channel", required=True, index=True)
    workspace_id = fields.Many2one(
        "bird.workspace", string="Workspace", related="channel_id.workspace_id", store=True, index=True
    )
    organization_id = fields.Many2one(
        "bird.organization", string="Organization", related="channel_id.organization_id", store=True, index=True
    )
    receiver_mobile = fields.Char(string="Receiver Mobile/Email", required=True, index=True)
    message_type = fields.Selection([
        ("template", "Template"),
        ("text", "Text"),
        ("image", "Image"),
        ("file", "File"),
        ("interactive", "Interactive"),
    ], string="Message Type", default="template", required=True, index=True)
    template_id = fields.Many2one("bird.template", string="Template", index=True)
    project_id = fields.Char(string="Project ID", index=True)
    version_id = fields.Char(string="Version ID")
    locale = fields.Char(string="Locale", default="en")
    parameters = fields.Text(string="Parameters")
    reference = fields.Char(string="Reference", index=True)
    body_text = fields.Text(string="Message Text")
    media_url = fields.Char(string="Media URL")
    filename = fields.Char(string="Filename")
    bulk_send_id = fields.Many2one("bird.bulk.send", string="Bulk Send", index=True, ondelete="set null")
    bulk_send_line_id = fields.Many2one("bird.bulk.send.line", string="Bulk Send Recipient", index=True, ondelete="set null")
    contact_id = fields.Many2one("bird.contact", string="Bird Contact", index=True, ondelete="set null", copy=False)
    contact_chatter_message_id = fields.Many2one(
        "mail.message", string="Contact Chatter Status", copy=False, readonly=True, ondelete="set null"
    )

    bird_message_id = fields.Char(string="Bird Message ID", index=True, copy=False)
    bird_status = fields.Char(string="Bird Status", copy=False)
    http_status = fields.Integer(string="HTTP Status", copy=False)

    status = fields.Selection([
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("read", "Read"),
        ("failed", "Failed"),
    ], string="Status", default="queued", required=True, index=True, copy=False)
    error_message = fields.Text(string="Error Message", copy=False)
    failure_code = fields.Char(string="Failure Code", copy=False, index=True)
    failure_reason = fields.Text(string="Failure Reason", copy=False)
    request_payload = fields.Text(string="Request Payload", copy=False)
    bird_response = fields.Text(string="Bird API Response", copy=False)

    send_date = fields.Datetime(string="Sent At", copy=False)
    delivered_at = fields.Datetime(string="Delivered At", copy=False)
    read_at = fields.Datetime(string="Read At", copy=False)
    failed_at = fields.Datetime(string="Failed At", copy=False)
    retry_count = fields.Integer(string="Retry Count", default=0, copy=False)
    last_retry_at = fields.Datetime(string="Last Retry At", copy=False)
    last_status_check_at = fields.Datetime(string="Last Status Check", copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        Contact = self.env['bird.contact'].sudo()
        for vals in vals_list:
            if not vals.get('contact_id') and vals.get('channel_id') and vals.get('receiver_mobile'):
                channel = self.env['bird.channel'].sudo().browse(vals['channel_id']).exists()
                if channel:
                    normalized = Contact._normalize_phone(vals.get('receiver_mobile'))
                    if normalized:
                        contact = Contact.search([
                            ('workspace_id', '=', channel.workspace_id.id),
                            ('normalized_number', '=', normalized),
                        ], limit=1)
                        if contact:
                            vals['contact_id'] = contact.id
        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)
        if set(vals) & {
            'status', 'bird_status', 'failure_code', 'failure_reason', 'error_message',
            'delivered_at', 'read_at', 'failed_at', 'contact_id', 'template_id',
        }:
            self._sync_contact_chatter_status()
        return result

    def _friendly_failure_reason(self):
        self.ensure_one()
        code = str(self.failure_code or '').strip()
        raw = (self.failure_reason or self.error_message or '').strip()
        if code == '131049':
            suffix = (' — %s' % raw) if raw and raw.lower() not in ('capacity', '131049') else ''
            return _('Meta delivery restriction (131049): WhatsApp did not deliver this message due to ecosystem engagement/capacity controls%s') % suffix
        if code == '15012':
            return _('WhatsApp delivery failure (15012)%s') % ((': %s' % raw) if raw else '')
        if code:
            return _('WhatsApp delivery failure (%s)%s') % (code, ((': %s' % raw) if raw else ''))
        return raw or _('Bird/WhatsApp reported delivery failure.')

    def _status_display(self):
        self.ensure_one()
        status = self.status or 'queued'
        return {
            'queued': ('⏳', _('Queued / Processing')),
            'sent': ('✓', _('Submitted to WhatsApp')),
            'delivered': ('✅', _('Delivered')),
            'read': ('👁️', _('Read')),
            'failed': ('❌', _('Delivery Failed')),
        }.get(status, ('•', status.title()))

    def _sync_contact_chatter_status(self):
        """Keep one chatter note per outbound Bird log and update it as webhooks arrive.

        This deliberately posts on ``bird.contact`` only. Bird contacts remain isolated
        from ``res.partner`` unless the user explicitly links/integrates them later.
        """
        for log in self.sudo():
            contact = log.contact_id
            if not contact and log.channel_id and log.receiver_mobile:
                normalized = self.env['bird.contact']._normalize_phone(log.receiver_mobile)
                contact = self.env['bird.contact'].sudo().search([
                    ('workspace_id', '=', log.workspace_id.id),
                    ('normalized_number', '=', normalized),
                ], limit=1)
                if contact:
                    # bypass our status-based write callback recursion by writing only contact_id;
                    # the callback is harmless but would run twice.
                    super(BirdMessageLog, log).write({'contact_id': contact.id})
            if not contact:
                continue

            icon, label = log._status_display()
            template_name = log.template_id.display_name if log.template_id else False
            channel_name = log.channel_id.display_name if log.channel_id else ''
            detail_lines = [
                '<div><strong>%s WhatsApp</strong> — <strong>%s</strong></div>' % (escape(icon), escape(label)),
            ]
            if template_name:
                detail_lines.append('<div><strong>%s:</strong> %s</div>' % (escape(_('Template')), escape(template_name)))
            detail_lines.append('<div><strong>%s:</strong> %s</div>' % (escape(_('To')), escape(log.receiver_mobile or '')))
            if channel_name:
                detail_lines.append('<div><strong>%s:</strong> %s</div>' % (escape(_('Channel')), escape(channel_name)))
            if log.reference:
                detail_lines.append('<div><strong>%s:</strong> %s</div>' % (escape(_('Reference')), escape(log.reference)))
            if log.bird_message_id:
                detail_lines.append('<div><strong>%s:</strong> %s</div>' % (escape(_('Bird Message ID')), escape(log.bird_message_id)))
            if log.status == 'failed':
                detail_lines.append(
                    '<div style="margin-top:4px;color:#b42318"><strong>%s:</strong> %s</div>' %
                    (escape(_('Reason')), escape(log._friendly_failure_reason()))
                )
            elif log.status == 'delivered' and log.delivered_at:
                detail_lines.append('<div><small>%s %s</small></div>' % (escape(_('Delivered at')), escape(str(log.delivered_at))))
            elif log.status == 'read' and log.read_at:
                detail_lines.append('<div><small>%s %s</small></div>' % (escape(_('Read at')), escape(str(log.read_at))))

            body = Markup('<div class="o_bird_whatsapp_delivery_status">%s</div>') % Markup(''.join(detail_lines))
            msg = log.contact_chatter_message_id.sudo().exists()
            if msg:
                msg.write({'body': body})
            else:
                msg = contact.message_post(
                    body=body,
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
                super(BirdMessageLog, log).write({'contact_chatter_message_id': msg.id})

    def _extract_message_id(self, data):
        if not isinstance(data, dict):
            return False
        return data.get("id") or data.get("messageId") or data.get("message_id") or False

    def _extract_bird_status(self, data):
        if not isinstance(data, dict):
            return False
        status = data.get("status")
        if isinstance(status, dict):
            return status.get("code") or status.get("value") or status.get("status") or False
        return status or False

    def _map_status(self, raw_status):
        value = str(raw_status or "").strip().lower().replace("-", "_")
        if not value:
            return False
        if value in {"read", "opened", "viewed"} or "read" in value or "opened" in value:
            return "read"
        if value == "delivered" or "delivered" in value:
            return "delivered"
        if "fail" in value or "reject" in value or "undeliver" in value or value in {"expired", "error"}:
            return "failed"
        if value in {"accepted", "pending", "queued", "processing", "sent", "sending", "submitted"}:
            return "sent" if value in {"accepted", "sent", "submitted"} else "queued"
        return False

    def _apply_api_result(self, result, sending=False):
        self.ensure_one()
        data = result.get("data") or {}
        raw_status = self._extract_bird_status(data)
        mapped = self._map_status(raw_status)
        now = fields.Datetime.now()
        vals = {
            "http_status": result.get("status_code") or 0,
            "bird_response": self.env["bird.api.service"].pretty_json(data),
            "bird_message_id": self._extract_message_id(data) or self.bird_message_id,
            "bird_status": raw_status or self.bird_status,
        }
        if sending:
            if result.get("ok"):
                vals.update({
                    "status": mapped or "sent",
                    "send_date": self.send_date or now,
                    "error_message": False,
                    "failed_at": False,
                })
            else:
                vals.update({
                    "status": "failed",
                    "failed_at": now,
                    "error_message": result.get("error") or "Unknown Bird API error",
                })
        elif result.get("ok"):
            vals["last_status_check_at"] = now
            if mapped:
                vals["status"] = mapped
                if mapped == "delivered" and not self.delivered_at:
                    vals["delivered_at"] = now
                elif mapped == "read" and not self.read_at:
                    vals["read_at"] = now
                elif mapped == "failed" and not self.failed_at:
                    vals["failed_at"] = now
        else:
            vals["last_status_check_at"] = now
            vals["error_message"] = result.get("error") or self.error_message
        self.sudo().write(vals)

    def _sync_bulk_send_line(self):
        for log in self:
            line = log.bulk_send_line_id.sudo()
            if not line:
                continue
            vals = {'message_log_id': log.id}
            if log.status == 'queued':
                vals['state'] = 'submitted'
            elif log.status == 'sent':
                vals.update({'state': 'sent', 'sent_at': log.send_date or fields.Datetime.now()})
            elif log.status == 'delivered':
                vals.update({'state': 'delivered', 'sent_at': log.send_date or line.sent_at, 'delivered_at': log.delivered_at or fields.Datetime.now()})
            elif log.status == 'read':
                vals.update({'state': 'read', 'sent_at': log.send_date or line.sent_at, 'delivered_at': log.delivered_at or line.delivered_at, 'read_at': log.read_at or fields.Datetime.now()})
            elif log.status == 'failed':
                no_auto_retry = str(log.failure_code or '') in {'131049', '15012'}
                vals.update({'state': 'failed', 'error_message': log.error_message or log.failure_reason or log.bird_status, 'failure_code': log.failure_code, 'failure_reason': log.failure_reason or log.error_message, 'auto_retry_allowed': not no_auto_retry})
            line.write(vals)
            if line.batch_id:
                line.batch_id._finish_if_complete()

    def action_refresh_status(self):
        for record in self:
            if not record.bird_message_id:
                raise UserError(_("This log has no Bird Message ID yet."))
            workspace = record.workspace_id
            organization = record.organization_id
            result = self.env["bird.api.service"].get(
                path=f"/workspaces/{workspace.workspace_id}/channels/{record.channel_id.channel_id}/messages/{record.bird_message_id}",
                access_key=organization.access_key,
                timeout=organization.request_timeout,
            )
            record._apply_api_result(result, sending=False)
        return True

    def action_retry(self):
        self.ensure_one()
        if not self.request_payload:
            raise UserError(_("There is no saved request payload to retry."))
        try:
            payload = json.loads(self.request_payload)
        except Exception as exc:
            raise UserError(_("Saved request payload is not valid JSON: %s") % exc)

        workspace = self.workspace_id
        organization = self.organization_id
        result = self.env["bird.api.service"].post(
            path=f"/workspaces/{workspace.workspace_id}/channels/{self.channel_id.channel_id}/messages",
            access_key=organization.access_key,
            payload=payload,
            timeout=organization.request_timeout,
        )
        self.sudo().write({
            "retry_count": self.retry_count + 1,
            "last_retry_at": fields.Datetime.now(),
        })
        self._apply_api_result(result, sending=True)
        return {
            "type": "ir.actions.act_window",
            "res_model": "bird.message.log",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def _cron_refresh_pending_status(self):
        now = fields.Datetime.now()
        organizations = self.env["bird.organization"].sudo().search([
            ("state", "=", "active"),
            ("auto_refresh_message_status", "=", True),
        ])
        for organization in organizations:
            if not organization._is_due(organization.last_message_status_refresh, organization.message_status_interval, now=now):
                continue
            records = self.sudo().search([
                ("organization_id", "=", organization.id),
                ("bird_message_id", "!=", False),
                ("status", "in", ["queued", "sent"]),
            ], order="last_status_check_at asc, create_date asc", limit=100)
            for record in records:
                try:
                    record.action_refresh_status()
                except Exception:
                    continue
            organization.write({"last_message_status_refresh": now})
        return True
