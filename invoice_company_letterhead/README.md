# Invoice Company Letterhead - Odoo 18 - V5.2

Based on stable V5.

For `Print with Company Letterhead` only, the existing company Top/Bottom
fields are now passed to wkhtmltopdf as real `margin-top` / `margin-bottom`.
This makes the PDF engine paginate invoice lines inside the usable stationery
area before the company PDF is merged.

Normal Odoo Print > PDF is unchanged.
