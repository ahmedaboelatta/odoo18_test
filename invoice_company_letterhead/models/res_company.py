from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    invoice_letterhead_enabled = fields.Boolean(
        string='Enable Invoice Letterhead',
        help='Use a custom letterhead background for customer invoices and credit notes.'
    )
    invoice_letterhead_image = fields.Binary(
        string='Invoice Letterhead',
        attachment=True,
        help='Upload an A4 PNG/JPG letterhead image containing the company header and footer.'
    )
    invoice_letterhead_filename = fields.Char(string='Letterhead Filename')
    invoice_letterhead_top_margin = fields.Float(
        string='Top Content Margin (mm)',
        default=35.0,
        help='Reserved top space for the printed letterhead header.'
    )
    invoice_letterhead_bottom_margin = fields.Float(
        string='Bottom Content Margin (mm)',
        default=25.0,
        help='Reserved bottom space for the printed letterhead footer.'
    )
