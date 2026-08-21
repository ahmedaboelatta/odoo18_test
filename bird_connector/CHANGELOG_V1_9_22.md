# Bird Connector V1.9.22

## Bird Contact identity synchronization

- Reworked manual Bird Contact synchronization to use Bird Contacts API search-by-identifier first.
- Searches with the canonical `phonenumber` identifier in E.164 format.
- Reuses the existing Bird Contact ID when the number already exists in Bird.
- Creates a Bird contact with `displayName` + `phonenumber` when no match exists.
- Handles duplicate/race responses by searching once more before reporting an error.
- Keeps a compatibility fallback for Bird tenants exposing the older GET-style search example.
- Stores the returned Bird Contact ID, sync status, sync timestamp and sync error in Odoo.
