# Bird Connector 1.9.50 — Dedicated Webhook Readiness Detection

## Fixed
- `proxy_mode=False` on the Odoo worker serving the backend UI no longer creates
  a false `Ready with Recommendations` state after a real Bird webhook has
  already proven end-to-end routing to the correct database.
- Deployment diagnostics now explicitly distinguish the current Odoo/UI process
  from the process that may receive `/bird/webhook/*`.
- Added `Webhook Proxy Assessment` to explain whether proxy mode is enabled on
  the current process or is irrelevant because the webhook route is already
  runtime-proven.
- The successful deployment state is now labelled `Ready for Production`.

## Safety
- HTTPS and database-routing failures remain blockers.
- Missing webhook runtime proof remains a recommendation.
- Signature verification remains a recommendation when signature checking is
  enabled but no received event has verified successfully.
- No server, Nginx, systemd, database-name, domain, or port value is hard-coded.
