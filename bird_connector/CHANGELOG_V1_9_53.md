# Bird Connector v1.9.53

- Outbound inbox images/documents are uploaded to Bird channel-media first via presigned upload.
- Bird-hosted `mediaUrl` is used for message delivery and retry, removing dependency on Odoo public media URL/db routing.
- File messages now include `contentType`, as required by the Bird Channels message schema.
- Image messages include `altText`.
- Local media binary remains stored for Odoo inbox preview/download.
