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
