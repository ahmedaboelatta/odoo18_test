# Bird Connector — Production Webhook Deployment

## Why use a dedicated webhook process?

The `/bird/webhook/` endpoint should remain available even when the main Odoo
workers are busy. A small dedicated Odoo process is recommended for the public
Bird callback path.

The dedicated process uses the **same database and addons** as the main Odoo
instance. It is not a separate registry. Therefore every installed custom module
must still keep its Python fields and PostgreSQL schema synchronized.

Bird Connector 1.9.47 additionally disables mail/chatter tracking while
processing webhooks so unrelated `mail.thread` pre-commit side effects do not
turn a valid Bird callback into an HTTP 500.

## Dedicated Odoo config

Copy the normal Odoo configuration and change only the deployment-specific
values. Do not hard-code the database/domain in the addon itself.

Recommended additions/overrides:

```ini
[options]
http_port = 8070
dbfilter = ^YOUR_DATABASE_NAME$
list_db = False

# IMPORTANT: only the main Odoo service should execute scheduled actions.
max_cron_threads = 0

# Recommended when the process is behind Nginx.
proxy_mode = True

logfile = /var/log/odoo/odoo-bird-webhook.log
```

Keep the same `addons_path`, PostgreSQL connection settings and Odoo code version
as the main service.

## Nginx routing

Route only the Bird webhook prefix to the dedicated process:

```nginx
location ^~ /bird/webhook/ {
    proxy_pass http://127.0.0.1:8070;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_redirect off;
}
```

All other requests remain routed to the normal Odoo HTTP port.

## Upgrade procedure

Whenever Python code or another installed addon is upgraded:

1. Upgrade the addon on the target database.
2. Confirm there are no schema errors in the main Odoo log.
3. Restart/reload the **main Odoo service**.
4. Restart the **dedicated Bird webhook service/process** too.
5. Confirm port 8070 is listening.
6. Send a real WhatsApp test message and confirm `/bird/webhook/...` returns 200.
7. Confirm the message appears in Bird Connector → Conversations.

A dedicated process that was not restarted can keep an old Python registry and
produce errors such as `AttributeError: model has no attribute ...`.

## Important limitation

A dedicated process protects capacity and isolates cron execution, but because it
uses the same Odoo database it cannot protect against a globally inconsistent
database schema. Never deploy a custom module whose Python fields exist before
the corresponding database upgrade completes.
