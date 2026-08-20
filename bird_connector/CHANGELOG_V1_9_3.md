# Bird Connector V1.9.3

## Bird Contacts
- Added a dedicated `bird.contact` model, fully separate from Odoo `res.partner`.
- Incoming WhatsApp webhooks automatically create or update a Bird Contact by workspace + normalized WhatsApp number.
- Incoming messages update last message / last activity and increment an unread counter.
- Contacts keep the Bird contact ID, workspace, last channel and optional manual link to an existing Odoo contact.
- No Odoo business/accounting contact is created automatically.

## Contact Tags
- Added `bird.contact.tag` with name and Odoo tag color.
- Each Bird Contact can carry multiple tags.
- Tags can be created directly from the contact or maintained from the Contact Tags menu.

## UI
- Added Contacts and Contact Tags menus inside Bird Connector.
- Added list/form/search views, unread filter, tag/channel/workspace grouping and Mark Read / Archive actions.

## Webhooks
- Inbound `whatsapp.inbound` processing now upserts Bird Contacts after signature validation and before the event is marked processed.
