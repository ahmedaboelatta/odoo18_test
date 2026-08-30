import base64
from urllib.parse import quote

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import pdf
import io


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
    invoice_letterhead_filename = fields.Char(string='Letterhead Filename')
    invoice_letterhead_top_offset = fields.Float(
        string='Letterhead Top Reserved Space (mm)',
        default=35.0,
        help='Optional extra vertical spacing before the invoice content. Normally leave this at 0.'
    )
    invoice_letterhead_bottom_offset = fields.Float(
        string='Letterhead Bottom Reserved Space (mm)',
        default=20.0,
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
                    raise ValidationError(_('The invoice letterhead PDF does not contain any pages.'))
            except ValidationError:
                raise
            except Exception as exc:
                raise ValidationError(_('The uploaded invoice letterhead is not a valid PDF file.')) from exc

    def action_preview_invoice_letterhead(self):
        self.ensure_one()
        if not self.invoice_letterhead_pdf:
            raise ValidationError(_('Please upload an invoice letterhead PDF first.'))
        filename = quote(self.invoice_letterhead_filename or 'invoice_letterhead.pdf')
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/res.company/{self.id}/invoice_letterhead_pdf/{filename}?download=false',
            'target': 'new',
        }

    def action_edit_letterhead_qweb(self):
        self.ensure_one()
        xmlid = self.env.context.get('letterhead_qweb_xmlid')
        allowed = {
            'invoice_company_letterhead.report_saleorder_letterhead_document',
            'invoice_company_letterhead.report_delivery_letterhead_document',
            'invoice_company_letterhead.report_invoice_letterhead_document',
            'purchase.report_purchaseorder_document',
        }
        if xmlid not in allowed:
            raise ValidationError(_('Unknown or unsupported report template.'))
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            raise ValidationError(_('The requested QWeb template is not installed: %s') % xmlid)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Edit Report QWeb'),
            'res_model': 'ir.ui.view',
            'res_id': template.id,
            'view_mode': 'form',
            'target': 'current',
        }
