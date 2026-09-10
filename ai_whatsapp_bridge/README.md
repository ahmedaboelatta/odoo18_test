# AI WhatsApp Bridge

Standalone Odoo 18 addon that forwards stored inbound Bird WhatsApp text messages to a brand-specific n8n webhook.

## Configuration

1. Install `bird_connector`, then install this addon.
2. Open **Bird Connector > Configuration > AI Integration > Brand Profiles**.
3. Create one profile per brand/channel and configure its n8n URL, secret header, timeout, and auto-reply preference.
4. Enable the profile. The master switch is available under Odoo General Settings > AI WhatsApp Bridge.

Each Bird WhatsApp channel can be assigned to one profile. Adding another brand requires only another profile; no code changes are needed.

## n8n request

The bridge sends the required message fields plus `brand_code` and `brand_name` so one workflow can route several brands.

```json
{
  "message_id": "...",
  "direction": "incoming",
  "brand_code": "zed_meals",
  "brand_name": "ZED Meals",
  "channel_name": "...",
  "channel_phone": "...",
  "customer_phone": "...",
  "message_type": "text",
  "text": "...",
  "conversation_id": "..."
}
```

## n8n callback

The initial forwarding webhook does not consume an AI reply from its HTTP response. After generating the final reply, n8n must call:

```text
POST /ai_whatsapp/reply
Content-Type: application/json
X-AI-Bridge-Secret: <the profile secret>
```

The header name is configurable per Brand Profile. Its value must match that profile's Secret Header Value.

```json
{
  "message_id": "the incoming Bird message ID from the forwarding payload",
  "conversation_id": "the Odoo conversation ID from the forwarding payload",
  "customer_phone": "the customer phone from the forwarding payload",
  "reply_text": "The final customer-facing answer only"
}
```

Do not send model reasoning, chain-of-thought, or intermediate output. Unknown JSON fields are ignored and are not stored. Duplicate callbacks are rejected persistently.

Forwarding and reply errors are recorded under **AI Integration > Forwarding Logs** and are never raised back into Bird webhook processing.
