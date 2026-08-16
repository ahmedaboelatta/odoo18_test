# Bird Connector 18.0.1.6.1

- Fix WhatsApp preview image rendering by using Odoo `/web/image` for persisted template images instead of relying on data URLs inside the HTML field.
- Reduce the header image editor footprint to a compact 320x220 preview.
- `+ Variable` no longer returns the full-form reload client action; numbered placeholders remain auto-detected from the Body.
- Clarify legacy MessageBird Balance API authentication and detect when the same modern Bird Platform key is duplicated into the legacy balance-key field.
- Keep the Bird-style 320px WhatsApp preview and existing template submission/sync flow unchanged.
