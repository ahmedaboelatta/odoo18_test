import base64
from urllib.parse import quote

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import pdf
import io

from .terms_direction import get_terms_direction


class ResCompany(models.Model):
    _inherit = 'res.company'

    invoice_letterhead_enabled = fields.Boolean(
        string='Enable Company Letterhead',
        help='Use the uploaded company letterhead PDF for all supported reports.'
    )
    invoice_letterhead_pdf = fields.Binary(
        string='Portrait Company Letterhead PDF (A4)',
        attachment=True,
        help='Upload a PDF containing the company letterhead. The first page is used on the first report page. '
             'If the PDF has multiple pages, page 1 is used for the first report page and the last available '
             'letterhead page is reused for subsequent pages.'
    )
    landscape_letterhead_pdf = fields.Binary(
        string='Landscape Company Letterhead PDF (A4)',
        attachment=True,
        help='Upload the A4 landscape company letterhead PDF. This file is reserved for landscape reports.'
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
    letterhead_terms_conditions = fields.Html(
        string='Invoice Terms and Conditions',
        compute='_compute_letterhead_terms_conditions',
        inverse='_inverse_letterhead_terms_conditions',
        sanitize=True,
        help='Default terms and conditions printed on letterhead invoices. '
             'Invoice-specific terms take priority when present.'
    )
    letterhead_quotation_terms_conditions = fields.Html(
        string='Quotation Terms and Conditions',
        compute='_compute_letterhead_quotation_terms_conditions',
        inverse='_inverse_letterhead_quotation_terms_conditions',
        sanitize=True,
        help='Default terms and conditions printed on letterhead quotations and sales orders. '
             'Document-specific terms take priority when present.'
    )

    def _letterhead_terms_parameter_key(self):
        self.ensure_one()
        return 'invoice_company_letterhead.terms_conditions.%s' % self.id

    def _compute_letterhead_terms_conditions(self):
        parameters = self.env['ir.config_parameter'].sudo()
        for company in self:
            company.letterhead_terms_conditions = parameters.get_param(
                company._letterhead_terms_parameter_key(),
                default='',
            )

    def _inverse_letterhead_terms_conditions(self):
        parameters = self.env['ir.config_parameter'].sudo()
        for company in self:
            key = company._letterhead_terms_parameter_key()
            if company.letterhead_terms_conditions:
                parameters.set_param(key, company.letterhead_terms_conditions)
            else:
                parameters.search([('key', '=', key)]).unlink()

    def _letterhead_quotation_terms_parameter_key(self):
        self.ensure_one()
        return 'invoice_company_letterhead.quotation_terms_conditions.%s' % self.id

    def _compute_letterhead_quotation_terms_conditions(self):
        parameters = self.env['ir.config_parameter'].sudo()
        for company in self:
            company.letterhead_quotation_terms_conditions = parameters.get_param(
                company._letterhead_quotation_terms_parameter_key(),
                default='',
            )

    def _inverse_letterhead_quotation_terms_conditions(self):
        parameters = self.env['ir.config_parameter'].sudo()
        for company in self:
            key = company._letterhead_quotation_terms_parameter_key()
            if company.letterhead_quotation_terms_conditions:
                parameters.set_param(key, company.letterhead_quotation_terms_conditions)
            else:
                parameters.search([('key', '=', key)]).unlink()

    def _get_letterhead_terms_direction(self):
        self.ensure_one()
        return get_terms_direction(self.letterhead_terms_conditions)

    def _get_letterhead_quotation_terms_direction(self):
        self.ensure_one()
        return get_terms_direction(self.letterhead_quotation_terms_conditions)

    @api.constrains('invoice_letterhead_pdf', 'invoice_letterhead_filename')
    def _check_invoice_letterhead_pdf(self):
        for company in self:
            if not company.invoice_letterhead_pdf:
                continue
            filename = (company.invoice_letterhead_filename or '').lower()
            if filename and not filename.endswith('.pdf'):
                raise ValidationError(_('The company letterhead must be a PDF file.'))
            try:
                raw = base64.b64decode(company.invoice_letterhead_pdf)
                reader = pdf.PdfFileReader(io.BytesIO(raw), strict=False)
                if reader.getNumPages() < 1:
                    raise ValidationError(_('The company letterhead PDF does not contain any pages.'))
            except ValidationError:
                raise
            except Exception as exc:
                raise ValidationError(_('The uploaded company letterhead is not a valid PDF file.')) from exc

    @api.constrains('landscape_letterhead_pdf')
    def _check_landscape_letterhead_pdf(self):
        for company in self:
            if not company.landscape_letterhead_pdf:
                continue
            try:
                raw = base64.b64decode(company.landscape_letterhead_pdf)
                reader = pdf.PdfFileReader(io.BytesIO(raw), strict=False)
                if reader.getNumPages() < 1:
                    raise ValidationError(_('The landscape letterhead PDF does not contain any pages.'))
            except ValidationError:
                raise
            except Exception as exc:
                raise ValidationError(_('The uploaded landscape letterhead is not a valid PDF file.')) from exc

    def action_preview_invoice_letterhead(self):
        self.ensure_one()
        if not self.invoice_letterhead_pdf:
            raise ValidationError(_('Please upload a company letterhead PDF first.'))
        filename = quote(self.invoice_letterhead_filename or 'invoice_letterhead.pdf')
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/res.company/{self.id}/invoice_letterhead_pdf/{filename}?download=false',
            'target': 'new',
        }

    def action_preview_landscape_letterhead(self):
        self.ensure_one()
        if not self.landscape_letterhead_pdf:
            raise ValidationError(_('Please upload a landscape company letterhead PDF first.'))
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/res.company/{self.id}/landscape_letterhead_pdf/landscape_letterhead.pdf?download=false',
            'target': 'new',
        }

    def action_edit_letterhead_qweb(self):
        self.ensure_one()
        xmlid = self.env.context.get('letterhead_qweb_xmlid')
        allowed = {
            'invoice_company_letterhead.report_saleorder_letterhead_document',
            'invoice_company_letterhead.report_delivery_letterhead_document',
            'invoice_company_letterhead.report_invoice_letterhead_document',
            'invoice_company_letterhead.report_purchase_letterhead_document',
            'invoice_company_letterhead.report_payment_voucher_letterhead_document',
            'invoice_company_letterhead.report_journal_entry_letterhead_document',
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
