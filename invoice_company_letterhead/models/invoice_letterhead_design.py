import base64
import io

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import pdf


class InvoiceLetterheadDesign(models.Model):
    _name = 'invoice.letterhead.design'
    _description = 'Invoice Print Design'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        ondelete='cascade', index=True,
    )
    layout = fields.Selection([
        ('bilingual_classic', 'Bilingual Classic'),
        ('odoo_standard', 'Odoo Standard'),
    ], required=True, default='bilingual_classic')
    is_default = fields.Boolean(string='Default Design')
    letterhead_pdf = fields.Binary(string='Letterhead PDF', attachment=True)
    letterhead_filename = fields.Char()
    top_offset = fields.Float(string='Top Reserved Space (mm)', default=8.0)
    bottom_offset = fields.Float(string='Bottom Reserved Space (mm)', default=8.0)
    color = fields.Char(string='Accent Color', default='#2f6fa3')

    @api.constrains('is_default', 'company_id')
    def _check_single_default(self):
        for design in self.filtered('is_default'):
            duplicate = self.search_count([
                ('company_id', '=', design.company_id.id),
                ('is_default', '=', True),
                ('id', '!=', design.id),
            ])
            if duplicate:
                raise ValidationError(_('Only one default invoice design is allowed per company.'))

    @api.constrains('letterhead_pdf', 'letterhead_filename')
    def _check_letterhead_pdf(self):
        for design in self:
            if not design.letterhead_pdf:
                continue
            filename = (design.letterhead_filename or '').lower()
            if filename and not filename.endswith('.pdf'):
                raise ValidationError(_('The letterhead must be a PDF file.'))
            try:
                reader = pdf.PdfFileReader(
                    io.BytesIO(base64.b64decode(design.letterhead_pdf)), strict=False
                )
                if not reader.getNumPages():
                    raise ValidationError(_('The letterhead PDF does not contain any pages.'))
            except ValidationError:
                raise
            except Exception as exc:
                raise ValidationError(_('The uploaded letterhead is not a valid PDF file.')) from exc

    def action_preview(self):
        self.ensure_one()
        wizard = self.env['invoice.print.wizard'].create({
            'company_id': self.company_id.id,
            'design_id': self.id,
        })
        return wizard.action_preview()
