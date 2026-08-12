# Bird Connector V1.2

- Fix template sending HTTP 422 caused by numeric Touchpoints revision being used as the Channels API send version. Active templates now send using `version: latest` unless a UUID/resource version is available.
- Improved Bird API validation error details in message logs.
- Added resilient WhatsApp preview parser for standard blocks, nested headers, WhatsApp Flow content, generic content, images, footer and up to 3 buttons/actions.
- Added RTL rendering for Arabic previews and LTR rendering for other locales.
- Added rich preview to the Send Message wizard.
- Kept existing GET/sync structure and message audit logs intact.
