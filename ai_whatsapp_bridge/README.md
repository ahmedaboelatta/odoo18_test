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

## n8n auto-reply response

When auto-reply is enabled, return JSON with one of these string fields:

```json
{"reply_text": "Your reply"}
```

The bridge also accepts `reply`, `ai_reply`, or `output`, including those fields inside `data`, `result`, or `output` objects.

Forwarding and reply errors are recorded under **AI Integration > Forwarding Logs** and are never raised back into Bird webhook processing.
