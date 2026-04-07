# -*- coding: utf-8 -*-

from odoo import models, fields


class StockLocation(models.Model):
    _inherit = 'stock.location'

    value = fields.Float(
        string='Expected Goods Cost',
        help='Target value for the total cost of goods held in this location.',
        company_dependent=True,
        digits='Product Price',
    )
    location_tag_ids = fields.Many2many(
        'stock.location.tag',
        'stock_location_tag_rel',
        'location_id',
        'tag_id',
        string='Location Tags',
        help='Tags to categorize this location',
    )
