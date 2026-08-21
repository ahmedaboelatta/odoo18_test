# Bird Connector V1.9.24

- Single-recipient template sends now bypass Bulk Sends and are sent immediately.
- Bulk mode is reserved for 2+ recipients.
- Added progressive recipient preflight before bulk delivery.
- Preflight validates E.164-like WhatsApp numbers and ensures a real synced Bird Contact ID.
- Added Ready, Invalid Number and Sync Failed classifications/counters.
- Invalid/sync-failed recipients are excluded from delivery and retain a visible reason.
