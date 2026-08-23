# Bird Connector 1.9.54 — Clipboard, Download & Composer Reliability

## Fixed
- Removed CSS `min()` from the Inbox stylesheet to avoid Odoo/libSass style
  compilation failures and the fallback-to-old-style banner.
- Image Copy now reports success only after the modern Clipboard API actually
  accepts a PNG ClipboardItem; removed the unreliable `execCommand` image
  fallback that could say "Image copied" while copying nothing useful.
- Media Download now fetches the authenticated Odoo media response as a Blob
  and downloads an object URL, so PDFs/images are downloaded instead of being
  rendered or ignored by the browser.
- Added clearer download/copy errors with the HTTP failure when available.
- Added an always-visible Quick Replies lightning button beside the `+` button.
  The `+` menu still contains Quick Replies, and typing `/` still opens them.
- Added click propagation guards to attachment/quick-reply controls to avoid
  document-level popover closing racing with OWL click handlers.

## Preserved
- `+` menu: Document, Photo, Quick replies.
- `/shortcut` Quick Replies behavior.
- WhatsApp-style message action menu.
- Runtime/realtime Inbox behavior and deployment architecture.
