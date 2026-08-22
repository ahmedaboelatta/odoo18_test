# Bird Connector 18.0.1.9.28

## Portable deployment diagnostics
- Renamed the non-blocking deployment state to **Ready with Recommendations** so optional proxy advice is not presented as a broken deployment.
- Added **Detected Deployment** and **Deployment Recommendation** fields.
- Auto Detect continues to accept a successfully received Bird webhook as runtime proof that the current database is routable, making the module portable across single-DB, dedicated-worker and reverse-proxy deployments.
- No database name, domain, IP address or webhook port is hard-coded in the connector.

## Real-time status consistency
- Added monotonic Bird status handling. Late `processing` / `accepted` callbacks can no longer overwrite a later `delivered` / `read` state.
- Applied the same status precedence to API refresh responses and webhook callbacks.
- Bulk recipient state/counters and contact chatter continue to update from the message log write hook as soon as webhook status is applied.

## Webhook diagnostics
- Webhook Events now record Processing Attempts, Processed At and the Matched Message Log for easier troubleshooting.
- The minute reconciliation cron remains a fallback for callbacks that arrive before the outbound message transaction commits.
