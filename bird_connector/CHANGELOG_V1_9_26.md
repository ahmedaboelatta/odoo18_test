# Bird Connector V1.9.26

## Real-time delivery tracking
- Bird outbound / interaction webhooks now remain the primary source for message lifecycle updates.
- Message status changes automatically synchronize the related Bulk Send recipient state and counters.
- Added realtime backend notifications for Bird Messages, Bulk Sends, and Bird Contacts so open list/form views refresh when delivery/read/failure events arrive.
- Manual **Refresh State** remains available only as a fallback.
- Added monotonic status handling to prevent late `accepted` callbacks from downgrading a message already marked `delivered` or `read`.
- Added a one-minute reconciliation cron for webhook callbacks that arrive before the outbound message log transaction has committed.

## Campaign controls
- Added **Schedule At** for future campaign start time.
- Renamed execution size to **Batch Size**.
- Added **Batch Interval (Minutes)** to control the delay between batches.
- Added **Pause**, **Resume**, and **Cancel** campaign actions.
- Added `Paused` campaign state and **Next Batch At** visibility.
- The message wizard exposes campaign scheduling controls automatically for sends with two or more recipients.
- Manual **Process Next Batch** intentionally bypasses the schedule/interval for administrator testing or emergency processing.
