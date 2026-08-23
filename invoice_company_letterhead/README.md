# Invoice Company Letterhead - Odoo 18

Version 18.0.3.0.0

## V3 behaviour

This version deliberately keeps Odoo's original invoice printing untouched.

On an invoice, the **Print** menu contains two choices:

1. Odoo's normal invoice print action — unchanged.
2. **Print with Company Letterhead** — prints the same invoice body on the PDF letterhead configured on the invoice's company.

## Company configuration

Go to **Settings > Users & Companies > Companies**, open a company, then:

- Enable **Invoice Letterhead**.
- Upload an A4 PDF in **Invoice Letterhead PDF**.
- Save.
- Use **Preview Letterhead PDF** to check it.

Each company has its own independent PDF.

## Multi-page behaviour

- A one-page letterhead repeats on every invoice page.
- With a multi-page letterhead, page 1 is used on invoice page 1, subsequent matching pages are used when available, and the final letterhead page is reused for remaining invoice pages.

## Upgrade

Replace the existing addon directory, restart Odoo, then upgrade `invoice_company_letterhead`.
