# Bird Connector V1.9.17

- Bulk recipients now track asynchronous lifecycle: Submitted, Sent, Delivered, Read, Failed.
- Bulk success is based on WhatsApp delivery, not API acceptance.
- Webhook delivery failures update the related bulk recipient in real time.
- Failure code/reason are stored and shown on recipients.
- Meta/Bird engagement failure 131049 / capacity 15012 is marked non-auto-retryable.
- Bulk counters now distinguish submitted, delivered, read, failed and pending recipients.
