# Bird Connector V1.9.23

## Outbound Bird Contact identity guard

- Every outbound send now resolves the recipient to a real Bird Contact before calling the Messages API.
- Existing Odoo Bird contacts with no Bird Contact ID are synchronized automatically.
- Unknown direct recipients are created as Bird contacts in the current workspace/channel, normalized, and synchronized automatically.
- Message logs are linked to the resolved `bird.contact` from creation time.
- Bulk Send validates/synchronizes each recipient before sending so identity errors stay isolated to the affected line and follow the existing retry policy.
- Existing contacts are reactivated and their last channel is refreshed when used for outbound sending.

The Messages API continues to use `identifierValue` for delivery; the new guard ensures Bird CRM identity exists first without changing the proven delivery payload.
