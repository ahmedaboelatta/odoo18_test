# Bird Connector 1.9.10

- Fixed Odoo backend SCSS compilation by removing mixed-unit CSS `min()` expressions that are not supported by the Odoo 18 Sass compiler.
- Added a secure Odoo media proxy for protected Bird incoming `mediaUrl` resources; Bird AccessKey stays server-side.
- Inbox image/video/audio/document URLs now use the authenticated Odoo proxy, fixing broken previews for incoming Bird media.
- Added a 32 MB preview safety limit and Bird-domain allow-list to prevent the media endpoint from becoming a generic proxy.
- Simplified the channel selector label to `WhatsApp Channel` / `All Channels` while preserving multi-channel filtering.
