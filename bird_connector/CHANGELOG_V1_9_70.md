# Bird Connector v1.9.70

## Menu redesign
- Reorganized the application navigation into Inbox, Contacts, Campaigns, Templates, Analytics, and Configuration.
- Moved Quick Replies under Contacts.
- Kept Templates as a dedicated expandable section.
- Moved technical/setup pages under Configuration.

## Role-based permissions
- Added Bird Connector roles: User, Supervisor, Manager, Administrator.
- Roles inherit progressively: Supervisor > User, Manager > Supervisor, Administrator > Manager.
- User: inbox, contacts, tags, quick replies and required read-only reference data.
- Supervisor: User permissions plus Teams / Queues and Auto-Routing Rules.
- Manager: Supervisor permissions plus Templates, Campaigns and Analytics.
- Administrator: Manager permissions plus Organizations, Workspaces, Channels, Webhooks and configuration.
- Odoo System Administrators retain full access for upgrade/recovery safety.

## Safety
- Existing menu external IDs and action IDs were preserved.
- No Bird API, webhook, inbox, media, infinite-scroll or messaging business logic was changed.
