from odoo import api, models


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    @api.model_create_multi
    def create(self, vals_list):
        """Force the configured discount when a product rule is created."""
        prepared_vals_list = []

        for original_vals in vals_list:
            vals = dict(original_vals)
            pricelist_id = vals.get("pricelist_id")

            if pricelist_id:
                pricelist = self.env["product.pricelist"].browse(pricelist_id)
                is_product_rule = bool(
                    vals.get("product_tmpl_id")
                    or vals.get("product_id")
                    or vals.get("applied_on") in ("1_product", "0_product_variant")
                )

                if pricelist.auto_discount_enabled and is_product_rule:
                    vals.update(pricelist._get_auto_discount_rule_values())

            prepared_vals_list.append(vals)

        return super().create(prepared_vals_list)
