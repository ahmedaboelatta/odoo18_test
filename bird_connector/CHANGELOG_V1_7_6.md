# Bird Connector 18.0.1.7.6

- Refresh Balance now refreshes the current Odoo form automatically after a successful Bird Wallet API update, so Wallet Name, Balance, Currency and Last Sync appear immediately without manual F5.
- Sync Workspaces & Channels now refreshes the organization form when invoked directly from the Organization screen while preserving the existing tuple return for internal callers.
- Wallet API Response moved from the main Organization form to an admin-only Technical tab.
- Bird Wallet API balance logic from 1.7.5 is unchanged.
