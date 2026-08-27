from odoo import api, fields, models


class TechrarProductMapping(models.Model):
    _name = 'techrar.product.mapping'
    _description = 'Techrar Product Mapping'
    _order = 'techrar_name, techrar_external_id'

    techrar_external_id = fields.Char(string='Techrar Subscription ID', required=True, index=True)
    techrar_name = fields.Char(string='Techrar Name', required=True)
    product_id = fields.Many2one(
        'product.product', string='Odoo Product', domain=[('sale_ok', '=', True)], ondelete='restrict'
    )
    mapping_state = fields.Selection(
        [('unmapped', 'Unmapped'), ('mapped', 'Mapped')], compute='_compute_mapping_state', store=True
    )
    last_seen_at = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('techrar_mapping_external_id_unique', 'unique(techrar_external_id)',
         'A mapping already exists for this Techrar subscription ID.'),
    ]

    @api.depends('product_id')
    def _compute_mapping_state(self):
        for record in self:
            record.mapping_state = 'mapped' if record.product_id else 'unmapped'
