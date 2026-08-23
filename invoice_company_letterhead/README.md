# Invoice Company Letterhead — Odoo 18 — V6.1

Hotfix for V6.

V6 accidentally placed `invoice_letterhead_layout` between an
`@api.constrains(...)` decorator and its method, causing a Python SyntaxError
and an HTTP 500 while Odoo loaded the module.

V6.1 fixes the Python class structure and retains:
- Per-company Letterhead PDF
- Separate Print with Company Letterhead action
- Per-company Letterhead Invoice Layout selector
- Normal Odoo Print PDF untouched
- Standard invoice/ZATCA QR content preserved
