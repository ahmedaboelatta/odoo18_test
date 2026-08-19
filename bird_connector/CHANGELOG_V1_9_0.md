# Bird Connector 18.0.1.9.0

## Real-time webhooks foundation
- Added Bird Notifications API webhook subscription management.
- Creates WhatsApp inbound, outbound, and interaction subscriptions per connected WhatsApp channel.
- Added a public Odoo webhook endpoint per Bird Organization.
- Added Bird signature verification using messagebird-signature and messagebird-request-timestamp.
- Added Webhook Subscriptions and Webhook Events audit models/views.
- Outbound/interactions update existing Bird Message Logs in real time when a matching Bird Message ID is received.
- Inbound events are securely stored as raw events, ready for Conversations/Inbound Messages phase.
- Existing message-status polling remains available as a fallback.
