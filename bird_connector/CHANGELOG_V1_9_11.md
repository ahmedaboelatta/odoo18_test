# Bird Connector 1.9.11

- Fixed historical inbound media previews by recovering protected media URLs from stored webhook payloads when the database media_url field is empty.
- Added support for Bird media endpoints that return JSON metadata with a signed CDN/download URL before the binary file.
- Added click-to-expand image lightbox in the Conversations inbox.
- Added attachment sending directly from the inline conversation composer (images and common documents, up to 16 MB).
- Added secure signed public Odoo media URLs for Bird to fetch outbound attachments without exposing Bird credentials.
- Added image captions and attachment preview/removal before sending.
