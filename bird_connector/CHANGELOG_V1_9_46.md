# V1.9.46

- Closed conversations moved exclusively into the Lists popover.
- Clicking Closed conversations a second time clears the filter back to All.
- Added a one-minute recent inbound reconciliation safety net using Bird Channels API.
- Webhooks remain the realtime path; polling only fills messages missed by webhook delivery/routing.
- Reconciliation is idempotent by Bird message ID and limited to 50 recent messages per connected WhatsApp channel.
