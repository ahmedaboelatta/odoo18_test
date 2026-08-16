from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    auto_discount_enabled = fields.Boolean(
        string="Auto Discount",
        help="Automatically apply the default discount to every product rule added to this pricelist.",
    )
    default_discount_percent = fields.Float(
        string="Default Discount (%)",
        default=50.0,
        digits=(16, 2),
        help="Discount percentage automatically assigned to newly added products.",
    )

    @api.constrains("default_discount_percent")
    def _check_default_discount_percent(self):
        for pricelist in self:
            if not 0.0 <= pricelist.default_discount_percent <= 100.0:
                raise ValidationError(_("Default Discount must be between 0 and 100 percent."))

    def action_apply_auto_discount_to_existing(self):
        """Apply the configured discount to existing product/variant rules only."""
        for pricelist in self:
            product_rules = pricelist.item_ids.filtered(
                lambda line: line.applied_on in ("1_product", "0_product_variant")
            )
            if product_rules:
                product_rules.write(pricelist._get_auto_discount_rule_values())
        return True

    def _get_auto_discount_rule_values(self):
        self.ensure_one()
        return {
            "compute_price": "formula",
            "base": "list_price",
            "price_discount": self.default_discount_percent,
            "fixed_price": 0.0,
            "percent_price": 0.0,
            "base_pricelist_id": False,
            "price_round": 0.0,
            "price_surcharge": 0.0,
            "price_min_margin": 0.0,
            "price_max_margin": 0.0,
        }
