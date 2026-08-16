# Pricelist Auto Discount - Odoo 18

Adds two settings to each pricelist:

- **Auto Discount**: enables automatic pricing for newly added products.
- **Default Discount (%)**: discount percentage; default is 50%.

When enabled, every newly created product/product-variant rule in that pricelist is configured as:

- Compute Price: Formula
- Based on: Sales Price
- Discount: configured percentage

This keeps the pricelist price dynamic. If the product Sales Price changes later, the pricelist price changes automatically.

The **Apply to Existing Products** button can update current product rules in the pricelist to the same formula.
