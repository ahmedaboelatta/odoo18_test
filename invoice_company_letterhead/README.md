# Invoice Company Letterhead — Odoo 18 — V5

V5 fixes the report-action detection bug in V4.

## Root cause fixed
The extra print action in V4 reused Odoo's original `report_name`
(`account.report_invoice_with_payments`). Odoo could therefore resolve the report
reference as the original action, so the special letterhead rendering branch was
never activated.

V5 gives the extra action a unique report name:
`invoice_company_letterhead.report_invoice_letterhead`

That template then calls Odoo's standard invoice report. This keeps the original
invoice body and localization content, including Saudi/ZATCA QR/barcode content,
while allowing only the extra print action to suppress Odoo's external
header/footer and merge the company's uploaded PDF stationery.

Normal Odoo Print > PDF remains untouched.
