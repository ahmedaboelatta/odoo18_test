# V1.9.29 - WhatsApp Read Receipts

- Model WhatsApp read receipts separately from Bird delivery status.
- Keep message Status/Bird Status at Delivered while recording `Read` and `Read At`.
- Parse `whatsapp.interaction` webhook payloads and match them to Bird Message ID.
- Bulk recipients now expose Read + Read At independently; Read Count uses the receipt flag.
- Preserve backward compatibility with historical records whose state/status was `read`.
- Webhook Events expose Interaction Type for diagnostics.
