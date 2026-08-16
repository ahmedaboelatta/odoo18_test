# Bird Connector V1.7.4

- Fixed Bird Wallet Metrics request payload.
- Added required `periodStart`, `periodEnd`, and `periodGroup` fields.
- Uses month-to-date with daily grouping by default.
- Wallet API errors now include the exact request payload and Bird response for diagnostics.
