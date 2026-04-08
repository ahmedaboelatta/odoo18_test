from odoo import api, fields, models, _
import base64
import qrcode
from io import BytesIO


class AccountMove(models.Model):
    _inherit = 'account.move'

    qr_code_image = fields.Text("QR Code Image", compute="_compute_generate_qr_code",
                                store=True)

    @api.depends('invoice_date', 'amount_untaxed', 'amount_tax', 'amount_total')
    def _compute_generate_qr_code(self):
        for move in self:

            def tlv(tag, value):
                value_bytes = value.encode('utf-8')
                return bytes([tag, len(value_bytes)]) + value_bytes

            # Sample values; replace with real invoice values
            seller_name = move.company_id.name or ""
            vat_number = move.company_id.vat or ""
            timestamp = move.invoice_date.strftime('%Y-%m-%d') if move.invoice_date else ''
            invoice_total = str(move.amount_total)
            vat_total = str(move.amount_tax)

            qr_bytes = (
                tlv(1, seller_name) +
                tlv(2, vat_number) +
                tlv(3, timestamp) +
                tlv(4, invoice_total) +
                tlv(5, vat_total)
            )

            encoded = base64.b64encode(qr_bytes).decode('utf-8')

            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(encoded)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            # Save image to memory buffer
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qr_image_binary = base64.b64encode(buffer.getvalue())
            buffer.close()

            # Save to binary field
            move.qr_code_image = qr_image_binary

