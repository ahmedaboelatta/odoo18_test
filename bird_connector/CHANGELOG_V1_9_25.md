# Bird Connector V1.9.25

- Fixed Bulk Send completion semantics: a successfully submitted/accepted Bird message completes the queue item; delivery/read continue asynchronously through webhooks.
- `Sent Count` now includes submitted/accepted messages.
- Bulk progress now reaches 100% when all recipients are submitted or failed instead of waiting for delivery webhooks.
- Bulk state moves to Done / Completed with Errors after queue processing finishes and no longer remains Running while waiting for delivery.
- Removed Recipient Summary from the Send Message wizard UI while retaining the model field for compatibility.
