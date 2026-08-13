import os
import re

from odoo import api, fields, models, _


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)

        # Auto-rename only when the file is uploaded through our POS smart button.
        if (
            self.env.context.get("pos_attachment_upload")
            and self.env.context.get("pos_auto_rename_images")
        ):
            for attachment in attachments:
                if (
                    attachment.res_model == "pos.order"
                    and attachment.res_id
                    and (attachment.mimetype or "").startswith("image/")
                ):
                    order = self.env["pos.order"].browse(attachment.res_id).exists()
                    if order:
                        original_name = attachment.name or "image"
                        _stem, ext = os.path.splitext(original_name)
                        ext = ext or self._extension_from_mimetype(attachment.mimetype)

                        safe_ref = re.sub(
                            r"[^A-Za-z0-9_-]+",
                            "-",
                            order.name or order.pos_reference or f"POS-{order.id}",
                        ).strip("-")
                        local_date = fields.Date.context_today(order)
                        new_name = (
                            f"{safe_ref}_{local_date}_{attachment.id}{ext.lower()}"
                        )
                        attachment.with_context(
                            skip_pos_attachment_audit=True
                        ).write({"name": new_name})

        self._post_pos_attachment_created_messages(attachments)
        return attachments

    def unlink(self):
        audit_rows = []
        if not self.env.context.get("skip_pos_attachment_audit"):
            for attachment in self:
                if attachment.res_model == "pos.order" and attachment.res_id:
                    order = self.env["pos.order"].browse(attachment.res_id).exists()
                    if order:
                        audit_rows.append((order.id, attachment.name or _("Attachment")))

        result = super().unlink()

        if audit_rows:
            Order = self.env["pos.order"]
            for order_id, filename in audit_rows:
                order = Order.browse(order_id).exists()
                if order:
                    order.message_post(
                        body=_("POS attachment deleted: %s", filename),
                        subtype_xmlid="mail.mt_note",
                    )
        return result

    def _post_pos_attachment_created_messages(self, attachments):
        if self.env.context.get("skip_pos_attachment_audit"):
            return

        Order = self.env["pos.order"]
        for attachment in attachments:
            if attachment.res_model == "pos.order" and attachment.res_id:
                order = Order.browse(attachment.res_id).exists()
                if order:
                    order.message_post(
                        body=_("POS attachment uploaded: %s", attachment.name),
                        subtype_xmlid="mail.mt_note",
                    )

    @api.model
    def _extension_from_mimetype(self, mimetype):
        return {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
            "image/tiff": ".tiff",
        }.get(mimetype or "", "")
