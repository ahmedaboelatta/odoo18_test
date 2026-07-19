from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_techrar_subscription = fields.Boolean(
        string='Is Techrar Subscription',
        default=False,
        help='Indicates if this product is mapped to a Techrar subscription package.',
    )
    techrar_sub_id = fields.Char(
        string='Techrar Subscription ID',
        help='Stores the Techrar subscription package identifier.',
    )


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_techrar_subscription = fields.Boolean(
        string='Is Techrar Subscription',
        default=False,
        help='Indicates if this product is mapped to a Techrar subscription package.',
    )
