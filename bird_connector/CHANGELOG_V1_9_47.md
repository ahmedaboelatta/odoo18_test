# V1.9.47 — Production Webhook Hardening

- Webhook processing now runs with mail/chatter tracking disabled.
- Inbound reconciliation uses the same no-tracking context.
- Removed the invalid `tracking` parameter from `bird.conversation.assigned_user_id`.
- Added portable production deployment examples for a dedicated webhook process.
- Dedicated webhook process documentation requires `max_cron_threads = 0`.
- Documented that both main Odoo and dedicated webhook processes must be restarted after Python/module upgrades.
- No database name, domain, port or credentials are hard-coded in runtime addon logic.
