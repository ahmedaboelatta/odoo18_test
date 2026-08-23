import base64
import io
from urllib.parse import quote

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import pdf


class ResCompany(models.Model):
    _inherit = 'res.company'

    invoice_letterhead_enabled = fields.Boolean(
        string='Enable Invoice Letterhead',
        help='Use the uploaded PDF letterhead for customer invoices and credit notes.'
    )

    invoice_letterhead_pdf = fields.Binary(
        string='Invoice Letterhead PDF',
        attachment=True,
        help='Upload a PDF containing the company letterhead. The first page is repeated on all invoice pages. '
             'If the PDF has multiple pages, page 1 is used for the first invoice page and the last available '
             'letterhead page is reused for subsequent pages.'
    )

    invoice_letterhead_filename = fields.Char(
        string='Letterhead Filename'
    )

    invoice_letterhead_layout = fields.Selection(
        selection=[
            ('default', 'Use Company Default'),
            ('web.external_layout_standard', 'Light'),
            ('web.external_layout_boxed', 'Boxed'),
            ('web.external_layout_bold', 'Bold'),
            ('web.external_layout_striped', 'Striped'),
            ('web.external_layout_bubble', 'Bubble'),
            ('web.external_layout_wave', 'Wave'),
            ('web.external_layout_folder', 'Folder'),
        ],
        string='Letterhead Invoice Layout',
        default='default',
        required=True,
        help='Layout used only by Print with Company Letterhead. '
             'Normal Odoo invoice printing is not changed.',
    )

    invoice_letterhead_top_offset = fields.Float(
        string='Additional Top Offset (mm)',
        default=0.0,
        help='Optional extra vertical spacing before the invoice content. Normally leave this at 0.'
    )

    invoice_letterhead_bottom_offset = fields.Float(
        string='Additional Bottom Offset (mm)',
        default=0.0,
        help='Reserved for layout fine tuning. Normally leave this at 0.'
    )

    @api.constrains('invoice_letterhead_pdf', 'invoice_letterhead_filename')
    def _check_invoice_letterhead_pdf(self):
        for company in self:
            if not company.invoice_letterhead_pdf:
                continue

            filename = (company.invoice_letterhead_filename or '').lower()
            if filename and not filename.endswith('.pdf'):
                raise ValidationError(_('The invoice letterhead must be a PDF file.'))

            try:
                raw = base64.b64decode(company.invoice_letterhead_pdf)
                reader = pdf.PdfFileReader(io.BytesIO(raw), strict=False)
                if reader.getNumPages() < 1:
                    raise ValidationError(
                        _('The invoice letterhead PDF does not contain any pages.')
                    )
            except ValidationError:
                raise
            except Exception as exc:
                raise ValidationError(
                    _('The uploaded invoice letterhead is not a valid PDF file.')
                ) from exc

    def action_preview_invoice_letterhead(self):
        self.ensure_one()

        if not self.invoice_letterhead_pdf:
            raise ValidationError(
                _('Please upload an invoice letterhead PDF first.')
            )

        filename = quote(
            self.invoice_letterhead_filename or 'invoice_letterhead.pdf'
        )

        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content/res.company/{self.id}/'
                f'invoice_letterhead_pdf/{filename}?download=false'
            ),
            'target': 'new',
        }
