# Bird Connector V1.7.3

- Clear credential labels: Organization ID, Default Workspace ID, Workspace Access Key.
- Added separate Wallet API Key for organization-level wallet/reporting access.
- Wallet refresh uses Wallet API Key when set, otherwise falls back to Workspace Access Key.
- Improved 401/403 wallet diagnostics.
- Reorganized Organization form into Bird Connection and Billing & Wallet sections.
- Access keys are masked in the form.
