# Bird Connector 1.9.51 — Media & Inbox UX

## Media reliability
- Outbound signed media is now published under `/bird/webhook/media/...`, so the
  same database-specific dedicated webhook instance can serve Bird's media fetch
  requests on multi-database servers.
- The previous `/bird_connector/outbound_media/...` endpoint remains available
  for backward compatibility.
- File messages now include `contentType` in the Bird Channels payload, matching
  Bird's current Files API examples.
- Documents in the inbox are download-only instead of opening an unreliable
  inline preview/loading tab.
- Failed outbound messages expose Bird failure code/reason as status diagnostics.

## Inbox UX
- Removed the browser-native search clear icon, leaving one consistent X button.
- `Lists > All conversations` now resets Closed/Unread/Needs Reply/Mine/
  Unassigned plus Team/Tag list filters.
- Added WhatsApp-style per-message actions:
  - Text: Copy
  - Image: Copy image + Download
  - Document/media: Download
- Replaced the paperclip composer button with a `+` menu.
- Added Quick Replies to the `+` menu and `/` shortcut workflow.

## Quick Replies
- Added `bird.quick.reply` model and management screen.
- Replies support optional Channel and Team / Queue scoping.
- Selecting a quick reply inserts it into the composer; it is never sent
  automatically, so the agent can edit it before sending.
