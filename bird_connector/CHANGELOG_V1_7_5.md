# Bird Connector V1.7.5

- Replaced Reporting `/usage` balance logic with Bird Wallet API `GET /organizations/{organizationId}/wallets`.
- Reads Bird money objects using `amount * 10^exponent`.
- Selects configured Wallet ID first, then auto-detects the main wallet (`isMain=true`).
- Stores Wallet ID, Wallet Name, balance, currency, last sync time, source, and raw API response.
- Keeps Workspace Access Key and Wallet API Key separated.
