# Bird Connector 1.9.52 — Media Reliability & Inbox UI Fixes

## Fixed
- Removed the SCSS `min()` expression that can fail Odoo/libSass asset compilation.
- Text Copy now has a legacy clipboard fallback when `navigator.clipboard` is unavailable.
- Image Copy converts JPEG/WebP media to PNG before writing to the browser clipboard.
- Incoming Bird media is cached locally after the first successful protected fetch.
- Download runs in a hidden authenticated frame so the Inbox remains open.
- Outgoing images/documents now use Bird's official presigned-upload flow instead of
  requiring Bird to fetch an Odoo-hosted temporary URL.

## Expected result
- No red `Style error` after asset rebuild.
- Previously fetched incoming images/documents download quickly on subsequent actions.
- Outgoing image/PDF sends use Bird-hosted `mediaUrl` and should no longer fail because
  Bird cannot fetch the Odoo public media URL.
