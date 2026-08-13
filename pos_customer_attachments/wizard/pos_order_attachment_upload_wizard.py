import os
import re

from odoo import fields, models, _
from odoo.exceptions import UserError


class PosOrderAttachmentUploadWizard(models.TransientModel):
    _name = "pos.order.attachment.upload.wizard"
    _description = "Upload POS Order Attachment"

    order_id = fields.Many2one(
        "pos.order",
        string="POS Order",
        required=True,
        readonly=True,
    )
    file_data = fields.Binary(
        string="File",
        required=True,
        attachment=False,
    )
    file_name = fields.Char(
        string="File Name",
        required=True,
    )

    def action_upload(self):
        self.ensure_one()

        order = self.order_id.exists()
        if not order:
            raise UserError(_("The POS order no longer exists."))

        if not self.file_data:
            raise UserError(_("Please select a file to upload."))

        file_name = self.file_name or _("Attachment")

        # Keep the user's original extension, but normalize image names when enabled.
        if order.auto_rename_pos_attachments:
            _stem, ext = os.path.splitext(file_name)
            safe_ref = re.sub(
                r"[^A-Za-z0-9_-]+",
                "-",
                order.name or order.pos_reference or f"POS-{order.id}",
            ).strip("-")
            local_date = fields.Date.context_today(order)
            sequence = order.attachment_count + 1
            file_name = f"{safe_ref}_{local_date}_{sequence:02d}{ext.lower()}"

        attachment = self.env["ir.attachment"].with_context(
            skip_pos_attachment_audit=True
        ).create({
            "name": file_name,
            "datas": self.file_data,
            "res_model": "pos.order",
            "res_id": order.id,
            "company_id": order.company_id.id,
        })

        # This is the important part: the actual file is posted into the chatter.
        order.message_post(
            body=_("POS attachment uploaded: %s", attachment.name),
            attachment_ids=[attachment.id],
            subtype_xmlid="mail.mt_note",
        )

        return {"type": "ir.actions.act_window_close"}
