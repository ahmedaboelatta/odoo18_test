# cPanel Email & Domain Manager for Odoo 18

Connects an Odoo company to a cPanel account through UAPI (port 2083).

## Features

- Synchronize email accounts, quotas, usage and suspension flags.
- Create, delete, fully suspend/restore mailboxes, change passwords and quotas.
- Synchronize domains, document roots and HTTPS redirect status.
- Hosting disk usage, scheduled synchronization, capacity warnings and audit log.
- Multi-company record rules and separate User/Administrator groups.

## Setup

1. Install the module and grant **cPanel / Administrator** to the responsible user.
2. Open **cPanel > Servers**, enter the cPanel hostname, username and API token.
3. Keep SSL verification enabled. Use **Test Connection**, then **Synchronize Now**.

The token is masked in the UI and restricted to cPanel administrators. Protect the Odoo database and backups because Odoo configuration secrets are stored server-side.
