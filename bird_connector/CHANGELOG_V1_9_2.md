# Bird Connector V1.9.2

- Fixed Bird Notifications webhook signature verification to use the documented payload: `timestamp + "\n" + URL + "\n" + binary SHA256(body)`.
- Signature verification now prefers the exact public webhook URL registered with Bird, with reverse-proxy URL fallbacks.
- Added webhook Deployment Check diagnostics: HTTPS, database routing (`dbfilter`/`db_name`), Odoo proxy mode, received-event confirmation, and successful signature confirmation.
- Fixed Setup WhatsApp Webhooks client-side OWL error by returning a simple reload action after successful backend setup.
