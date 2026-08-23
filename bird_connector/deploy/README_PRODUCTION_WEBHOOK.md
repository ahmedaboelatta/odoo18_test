# Bird Connector — Production Webhook Deployment

## One-time server installer

Run once on each new server as root:

```bash
cd bird_connector/deploy
sudo bash install_bird_webhook.sh --db YOUR_DATABASE --domain odoo.example.com
```

Use `--dry-run` first on production if desired.

The installer detects the main Odoo configuration, Odoo user and `odoo-bin`,
copies the main config so DB credentials/addons paths stay aligned, creates the
dedicated webhook config, installs/enables the systemd service, optionally
updates the matching Nginx vhost, validates Nginx, restarts the dedicated
instance and checks that the webhook port is listening.

It creates timestamped backups before changing existing config, service or Nginx
files. It deliberately refuses to guess a database on a multi-database server.

The dedicated config enforces:

```ini
list_db = False
proxy_mode = True
max_cron_threads = 0
```

so the 8070 process receives Bird callbacks but does not execute Odoo scheduled
actions.

## Why this is outside module installation

Odoo addons should not have root permission to write `/etc`, modify Nginx or
control systemd. The addon remains portable; this installer performs the
privileged OS setup once on the target server.

## Upgrade rule

After any Python/schema-changing addon upgrade:
1. complete the DB upgrade successfully;
2. confirm there are no UndefinedColumn/schema errors;
3. restart the main Odoo service;
4. restart `odoo-bird-webhook.service`;
5. send a real WhatsApp test message and confirm HTTP 200 plus Inbox delivery.

## Options

`--db`, `--domain`, `--main-conf`, `--odoo-bin`, `--user`, `--group`,
`--port`, `--nginx-site`, `--skip-nginx`, `--dry-run`.

## Production readiness audit (v1.9.49+)

Before the first production deployment, and after major Odoo/service changes, run:

```bash
sudo bash check_bird_production_readiness.sh \
  --main-service odoo-main.service \
  --domain odoo.example.com
```

The audit is non-destructive. It checks Main Odoo process/service health, boot
persistence, duplicate Odoo services, Main/Bird port isolation, Bird cron
isolation, local HTTP health and Nginx webhook routing.

The installer now performs the same critical Main Odoo safety preflight before
it changes Bird configuration. It **never modifies the Main Odoo service**.
If the server uses a legacy SysV-generated Odoo service, nohup, or foreground
process, fix/convert Main Odoo first and then run the Bird installer.

Recommended order on a new production server:

```bash
# 1) Audit first
sudo bash check_bird_production_readiness.sh --main-service odoo-main.service --domain odoo.example.com

# 2) Preview Bird deployment
sudo bash install_bird_webhook.sh --db YOUR_DATABASE --domain odoo.example.com --main-service odoo-main.service --dry-run

# 3) Apply
sudo bash install_bird_webhook.sh --db YOUR_DATABASE --domain odoo.example.com --main-service odoo-main.service

# 4) Audit again
sudo bash check_bird_production_readiness.sh --main-service odoo-main.service --domain odoo.example.com
```
