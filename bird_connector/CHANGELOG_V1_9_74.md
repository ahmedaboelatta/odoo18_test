# v1.9.74

- Restored the native Odoo 18 navbar geometry by removing the previous navbar/overlay z-index overrides.
- Normalized Bird Inbox stacking contexts so Odoo section dropdown menus render above the Inbox.
- Kept Bird Lists, message action menus, quick replies and drag overlays above their local Inbox content only.
- No changes to Inbox logic, APIs, permissions, infinite scroll, media handling or menu structure.
