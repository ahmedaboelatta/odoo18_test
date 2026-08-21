# Bird Connector V1.9.21

- Automatically creates or resolves manually-created Bird Contacts in Bird Contacts API.
- Uses Bird create-or-update-by-identifier endpoint with the canonical `phonenumber` identifier to avoid duplicate Bird contacts.
- Stores the canonical Bird Contact ID immediately when Bird returns it.
- Adds Bird Sync Status, last sync time and last synchronization error fields.
- Adds a manual **Sync Bird Contact** button for retry/recovery.
- Bird API outages no longer prevent a local Bird Contact from being saved; the contact remains in Sync Error state and can be retried.
