# Bird Connector v1.9.8

- Added Closed filter to the split Conversation Inbox.
- Kept conversation list ordered newest-first and message history oldest-first.
- Added browser-local compact timestamps (Today / Yesterday / older dates).
- Added automatic scroll to latest message while preserving the reader position during silent refreshes.
- Added optimistic outgoing messages so Send appears immediately without page reload.
- Improved Needs Reply behavior and recomputation when conversation state changes.
- Added inbound image/video/audio/document metadata extraction and media rendering when Bird supplies a usable media URL.
- Added backward-compatible media metadata extraction from historical raw webhook payloads.
- Compact conversation rows, unread badges and closed badges.
