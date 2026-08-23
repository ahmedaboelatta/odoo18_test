# Bird Connector 1.9.53 — Inbox Media Actions & Popover Reliability

## Fixed
- Clicking outside Quick Replies now closes the Quick Replies picker.
- Clicking outside the `+` attachment menu now closes it.
- Clicking outside Lists and message action menus now closes them too.
- Message actions now follow the requested behavior:
  - Text: Copy
  - Image: Copy image + Download
  - Document/file: Download only
- Media Download now uses a real browser download anchor instead of a hidden iframe.
- Image Copy now uses the modern Clipboard API first and a rich `<img>` selection fallback when browsers block `ClipboardItem` image writes.
- Quick Replies popover is slightly more compact so it behaves more like a messaging app menu.

## Notes
- Browser security can still block programmatic image clipboard access in some environments.
  In that case Download remains available.
- No Bird API sending logic was changed in this UI patch; outgoing media should be re-tested after upgrade so any remaining Bird delivery failure can be diagnosed from the current API response.
