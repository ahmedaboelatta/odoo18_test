# Bird Connector 18.0.1.9.45

- Harden inbound WhatsApp webhook processing for Bird sender envelope variations.
- Recover channel context when the webhook subscription is external/unmatched.
- Reprocess failed inbound webhooks from the reconciliation cron instead of leaving them permanently pending.
- Add Closed conversations inside the WhatsApp-style Lists dropdown, with a live count.
