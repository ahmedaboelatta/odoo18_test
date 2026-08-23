# Invoice Company Letterhead - Odoo 18

Version 18.0.2.0.0

## What changed
- The letterhead is now uploaded as a real PDF, not an image.
- The normal Odoo company header/footer are bypassed for enabled customer invoices.
- After Odoo renders the invoice, the generated PDF is merged on top of the company's PDF letterhead.
- Works per `company_id` in multi-company databases.
- Includes a **Preview Letterhead PDF** button.
- No external Python package is required: it uses Odoo's own PDF compatibility layer.

## Configuration
1. Settings > Users & Companies > Companies.
2. Open the company.
3. Enable **Invoice Letterhead**.
4. Upload an A4 PDF in **Invoice Letterhead PDF**.
5. Save.
6. Use **Preview Letterhead PDF** to verify the uploaded file.
7. Print a customer invoice / credit note / receipt.

### Multi-page letterhead
- 1-page PDF: the same page is repeated for every invoice page.
- 2+ page PDF: page 1 is used on invoice page 1; later invoice pages use matching pages, then reuse the last letterhead page.
