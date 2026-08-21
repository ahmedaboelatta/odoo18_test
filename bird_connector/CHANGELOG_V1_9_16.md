# Bird Connector 1.9.16

- Fixed bulk template wizard validation when the template channel is readonly/derived from the template.
- Manual Bird Contact creation now defaults Organization and Workspace from the active Bird configuration.
- Bulk recipient chips are no longer rendered in the wizard; only the recipient count and a short summary are shown.
- Restored the Template Versions smart button beside Messages.
- Added persistent WhatsApp Bulk Send queues with recipient-level audit status.
- Bulk sends are processed gradually by a one-minute scheduler (10 recipients per run by default, configurable per batch).
- Added retry/cancel/process-next controls, progress counters, and links to generated Bird message logs.
- Added a Bulk Sends menu for monitoring large sends.
