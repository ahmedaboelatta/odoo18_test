# Bird Connector v1.9.52

- Close attachment, quick-reply, message-action and list menus when clicking outside them.
- Added Retry action for failed outbound inbox messages.
- Retry reuses the saved Bird message log payload when available and refreshes the same chat bubble with the latest status.
- Inbox now reads delivery status from the linked message log when available, preventing stale failed/delivered labels.
