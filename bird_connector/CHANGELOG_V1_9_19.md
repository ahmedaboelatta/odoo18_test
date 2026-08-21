# Bird Connector v1.9.19

- Self-heals missing `bird_message_log.contact_id` and `contact_chatter_message_id` database columns during module initialization/upgrade.
- Fixes `UndefinedColumn` / `InFailedSqlTransaction` errors when sending from a template or using **Process Next Batch**.
- Keeps the Technical tab compatible with Odoo 18 after the successful upgrade applies the latest view definition.
- Captures Bird's canonical receiver Contact ID from outbound message API responses. A Bird Contact created manually in Odoo will therefore receive its Bird Contact ID after Bird returns that identity on the first outbound message, without requiring the customer to reply first.
- Existing inbound-created Bird Contact IDs continue to work unchanged.
