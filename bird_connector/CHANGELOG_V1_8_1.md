# Bird Connector V1.8.1

## Configuration architecture cleanup
- Replaced the Bird section inside Odoo General Settings with a persistent `bird.configuration` model.
- Configuration now opens as a List view and then a clean tabbed Form view.
- Added General, Synchronization, Wallet, Technical, and Maintenance tabs.
- Existing V1.8.0 `ir.config_parameter` values are used as defaults when the initial configuration record is created.
- Only one configuration is active at a time; activating another preserves older records as inactive history.
- The active configuration continues to synchronize legacy config parameters so existing Bird services and template defaults remain compatible.
- Cron activation/intervals are updated automatically when the active configuration is saved.
- Template duplicate cleanup moved to the Maintenance tab.
- Old Bird `res.config.settings` inherited view is disabled.
