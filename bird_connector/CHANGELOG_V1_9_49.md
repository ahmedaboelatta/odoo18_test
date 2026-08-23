# Bird Connector 1.9.49 — Production Readiness Guardrails

## Added
- `deploy/check_bird_production_readiness.sh`: non-destructive production audit.
- Validates exactly one Main Odoo process and a separate Bird webhook process.
- Validates native systemd ownership, active/enabled boot persistence and port isolation.
- Detects extra enabled Odoo services that could cause duplicate 8069 listeners or duplicate cron execution.
- Validates dedicated Bird config: `list_db=False`, `proxy_mode=True`, `max_cron_threads=0`, `dbfilter` and port.
- Validates local Main/Bird HTTP responses, Nginx syntax and `/bird/webhook/` proxy route when discoverable.
- Clear `READY FOR PRODUCTION`, `READY WITH RECOMMENDATIONS`, or `NOT READY FOR PRODUCTION` summary.

## Installer hardening
- `install_bird_webhook.sh` now performs a **non-destructive Main Odoo preflight** before changing Bird/Nginx files.
- It refuses deployment when Main Odoo is missing, duplicated, unmanaged by systemd, disabled at boot, or using a non-native legacy service.
- It refuses deployment when another enabled Odoo service could collide with the main service.
- Main Odoo is never started, stopped, disabled, converted, or otherwise modified by the Bird installer.
- `--main-service NAME` can explicitly select the Main Odoo service.
- `--skip-main-preflight` exists for unusual environments, but is intentionally not recommended for production.
