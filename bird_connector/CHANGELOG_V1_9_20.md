# Bird Connector V1.9.20

## Phone normalization and country defaults

- Added **Default Contact Country** to each Bird Organization (Saudi Arabia by default).
- Manually entered local WhatsApp numbers are normalized to international E.164-style format on save.
- Saudi examples: `0501234567`, `501234567`, `966501234567`, `00966501234567` and `+966501234567` all normalize to `+966501234567`.
- The visible WhatsApp Number is stored in international format, while `normalized_number` remains the digits-only canonical lookup key.
- Normalization is applied consistently on create, edit, inbound upsert and before uniqueness checks.
- Existing Bird-provided international numbers are not double-prefixed.
