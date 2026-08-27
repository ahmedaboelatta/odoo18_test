# v1.9.78

- Make Bulk Send progress depend on recipient delivery states.
- Count only `delivered` and `read` recipients toward progress; failed recipients no longer increase it.
- Rename the field label to `Delivery Progress (%)` so the UI matches the calculation.
- Compute progress on read so existing campaigns immediately use the corrected value after upgrade.
