from odoo import models

from .terms_direction import get_terms_direction


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_letterhead_terms_direction(self):
        self.ensure_one()
        return get_terms_direction(self.note)
