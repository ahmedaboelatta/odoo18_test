# Bird Connector v1.9.54

- Fixed Retry for failed inbox images and documents.
- Retry no longer reuses an old saved Odoo `/bird_connector/outbound_media/...` URL.
- The original saved attachment binary is re-uploaded to Bird channel-media and a fresh Bird-hosted `mediaUrl` is used.
- Old failed media messages created before v1.9.53 can now be repaired by Retry when their local binary is available.
