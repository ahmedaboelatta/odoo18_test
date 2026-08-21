# Bird Connector V1.9.18

- Fixed Odoo 18 Technical tabs failing with `CodeEditor: mode is not valid` by removing the incompatible Ace `mode` option.
- Added Bird Contact chatter delivery tracking for outbound WhatsApp messages. One chatter note is created per message and updated in place as the lifecycle changes (Submitted, Delivered, Read, Failed).
- Delivery failures show the Bird/Meta failure code and a readable reason; Meta 131049 is labelled as a delivery restriction caused by WhatsApp ecosystem engagement/capacity controls.
- Message logs now resolve and store the related Bird Contact when possible, making delivery traceability easier.
- Bulk-send tracking remains webhook-driven: API acceptance is not treated as final delivery.
