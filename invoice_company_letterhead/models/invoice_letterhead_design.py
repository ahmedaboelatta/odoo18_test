from odoo import fields, models


class InvoiceLetterheadDesign(models.Model):
    """Legacy V6 storage kept only so upgrades can migrate its uploaded PDF."""

    _name = 'invoice.letterhead.design'
    _description = 'Legacy Invoice Print Design'
    _order = 'is_default desc, sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, ondelete='cascade')
    layout = fields.Selection([
        ('bilingual_classic', 'Bilingual Classic'),
        ('odoo_standard', 'Odoo Standard'),
    ])
    is_default = fields.Boolean()
    letterhead_pdf = fields.Binary(attachment=True)
    letterhead_filename = fields.Char()
    top_offset = fields.Float()
    bottom_offset = fields.Float()
    color = fields.Char()
    custom_css = fields.Text()
