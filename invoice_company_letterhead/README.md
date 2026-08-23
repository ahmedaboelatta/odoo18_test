# Invoice Company Letterhead — Odoo 18 — V4

## Printing
Odoo's original **Print > PDF** remains unchanged.

A second print action is added:
**Print with Company Letterhead**

## V4 fix
V4 explicitly passes `company_letterhead_print` into the QWeb rendering values.
This makes the second action use a body-only external layout, so Odoo's normal
logo/header/footer/bubble layout is not rendered into the letterhead version.

The standard invoice document is still used. Therefore localization additions
inside the invoice body — including the Saudi/ZATCA QR code when Odoo normally
provides it — are preserved rather than recreated manually.

The company's uploaded PDF is merged as the stationery/background after Odoo
renders the invoice body. The invoice page itself is never scaled.

## Multi-company
The PDF is selected from `move.company_id`, so each company can have its own stationery.
