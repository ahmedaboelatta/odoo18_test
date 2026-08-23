# Bird Connector V1.9.30

## UI cleanup
- Removed Read / Read At from Message Log list and form views.
- Removed the Read filter from Message Logs.
- Removed Read Count from Bulk Send form.
- Removed Read / Read At from Bulk Send recipient list.
- Delivery state remains aligned with Bird delivery statuses; read-receipt backend compatibility is retained for future use.
- Removed `read` from visible status bars/decorations while preserving backward-compatible backend data.

## Compatibility
- No database columns are removed. Existing V1.9.29 records remain valid.
- Webhook interaction diagnostics remain available under Webhook Events for technical troubleshooting.
