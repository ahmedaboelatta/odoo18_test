# Bird Connector V1.3

- Added WhatsApp Text messages.
- Added WhatsApp Image messages using public media URLs.
- Added WhatsApp File messages using public media URLs and optional filename/caption.
- Added one unified Send Message wizard with Template/Text/Image/File modes.
- Added E.164-style mobile normalization and validation.
- Added Refresh Status button using Bird Get Message endpoint.
- Added automatic status polling every 10 minutes for queued/sent messages.
- Added Retry action for failed messages using the exact saved request payload.
- Added message content fields and richer lifecycle/audit information to message logs.
- Preserved existing template send flow and backward-compatible message engine wrapper.
