# POS Customer Attachments — Odoo 18

Professional custom addon for customer-driven POS order attachment control.

## Workflow

1. Open a customer/contact.
2. Open **POS Attachment Policy**.
3. Enable **Require POS Order Attachments**.
4. Set the minimum number of required attachments.
5. Optional: enable automatic image renaming.
6. New POS orders created for that customer receive a permanent policy snapshot.
7. The POS order displays an **Attachments** smart button only when attachments are required.
8. Uploaded files are linked directly to `pos.order` through `ir.attachment`.
9. Upload/delete actions are logged in the order chatter.
10. Use the built-in search filters:
   - Attachment Required
   - With Attachments
   - Missing Attachments

## Important design choices

- Existing historical POS orders are NOT silently changed when the customer policy changes.
- No core Odoo or Enterprise files are modified.
- First release is warning/monitoring only; it does not block POS payment or invoicing.
- Attachment searches use SQL subqueries rather than loading all attachment IDs into Python.

## Install

Copy the folder `pos_customer_attachments` into your custom addons path, restart Odoo,
update the Apps List, then install **POS Customer Attachments**.

CLI upgrade example:

```bash
./odoo-bin -c odoo.conf -d YOUR_DATABASE -u pos_customer_attachments --stop-after-init
```

## Technical names

### res.partner
- `pos_attachment_required`
- `pos_minimum_attachments`
- `pos_auto_rename_attachments`

### pos.order
- `attachment_required`
- `minimum_required_attachments`
- `auto_rename_pos_attachments`
- `attachment_count`
- `has_attachment`
- `attachment_missing`
- `attachment_status`

## Odoo version

Built for Odoo 18.

## v18.0.1.1.1

- Fixed **With Attachments** filter.
- Fixed **Missing Attachments** filter.
- Replaced invalid SQL-object domains with explicit parameterized SQL lookup and standard Odoo ID domains.
