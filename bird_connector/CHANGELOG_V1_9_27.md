# Bird Connector 18.0.1.9.27

## Portable webhook deployment

- Added **Webhook Deployment Mode** with Auto Detect, Single Database / dbfilter, Multi Database - Dedicated Webhook Instance, and Multi Database - External / Proxy Routing.
- Deployment readiness no longer assumes that the UI worker and webhook worker use the same Odoo config.
- A successfully stored Bird webhook event is now accepted as runtime proof that the public webhook reached the current database.
- Added **Routing Evidence** to make the readiness decision transparent.
- `proxy_mode = False` remains a recommendation behind Nginx but no longer blocks a deployment whose routing is proven.
- Added in-product guidance explaining how to move the addon between single-database and multi-database servers without hard-coded database names, domains, or ports.
- No environment-specific database, domain, IP address, or Odoo port is embedded in the addon.
