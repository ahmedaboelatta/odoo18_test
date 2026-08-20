# Bird Connector V1.9.1

## Webhooks stabilization
- Fixed Odoo 18 OWL crash when opening a webhook subscription by replacing the statusbar renderer with a safe badge field.
- Added Webhook Base URL override per Organization for public HTTPS reverse-proxy/domain setups.
- Added HTTPS readiness indicator.
- Added ownership classification: Odoo Connector vs External / Existing.
- Sync now imports existing Bird subscriptions without treating n8n/other-system webhooks as connector-owned.
- Setup only reuses subscriptions managed by this connector, preventing accidental takeover of external webhooks.
- Removed the incorrect one-subscription-per-event/channel SQL constraint; Bird supports multiple URLs for the same event/channel.
- Sync requests up to 100 subscriptions and preserves external signing keys as unknown rather than copying the Odoo signing key.
- Deactivate action is restricted to connector-managed subscriptions.
- Fixed Bird webhook signature verification to use the binary SHA256 body digest documented by Bird.
- Webhook Event boolean fields are display-only in list view to avoid accidental toggles.
