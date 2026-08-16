# Bird Connector 18.0.1.7.0

- Added WhatsApp header types: None, Text, Image, Video, Document, Location.
- Added Bird media upload support for Image, Video and Document sample headers.
- Added preview cards for Video, Document and Location headers.
- Added Template Versions smart button and local version history model synchronized from Bird project channel templates.
- Versions list shows status, current/active marker, publisher, last update and Bird version ID.
- Kept Sync Template and Refresh Status as separate actions.
- Balance remains wired to the official legacy MessageBird Balance API and requires a compatible MessageBird access key; a modern Bird Platform access key may return 401.
