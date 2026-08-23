# Invoice Company Letterhead - Odoo 18

Adds a company-specific invoice letterhead for multi-company databases.

## Configuration
1. Go to Settings > Users & Companies > Companies.
2. Open a company.
3. In Invoice Letterhead:
   - Enable Invoice Letterhead.
   - Upload an A4 portrait PNG/JPG containing the complete header/footer design.
   - Set top/bottom content margins in mm.
4. Save and print a Customer Invoice or Credit Note.

The invoice automatically uses the letterhead of `invoice.company_id`.
If the feature is disabled or no image is uploaded, the standard Odoo external layout is used.

Recommended image size: 2480 x 3508 pixels (A4 at 300 DPI).
