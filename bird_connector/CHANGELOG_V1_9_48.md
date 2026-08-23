# Bird Connector 1.9.48 — Portable Deployment Installer

- Added `deploy/install_bird_webhook.sh`.
- Auto-detects the main Odoo config, service user and `odoo-bin`.
- Creates the dedicated config from the main config while forcing a single DB,
  `list_db=False`, `proxy_mode=True`, `max_cron_threads=0` and a dedicated log.
- Installs/enables/restarts the dedicated systemd service.
- Can auto-detect and safely update the Nginx vhost by domain.
- Validates Nginx before reload and verifies the dedicated port after start.
- Makes timestamped backups before changing OS configuration.
- Supports `--dry-run` and explicit overrides for production environments.
