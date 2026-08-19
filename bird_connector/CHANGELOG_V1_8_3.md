# Bird Connector 18.0.1.8.3

- Moved connector configuration from the standalone Configuration screen onto each Bird Organization.
- Added per-organization auto sync, message status refresh, wallet refresh, intervals, default locale, API timeout, and debug response controls.
- Added last-run timestamps for scheduled jobs.
- Scheduled actions now run as 5-minute dispatchers and respect each organization's own settings/intervals.
- Added a low-wallet-balance ribbon driven by each organization's threshold.
- Moved duplicate-template cleanup into the Organization Maintenance tab.
- Removed the standalone Configuration menu and the floating Active toggle from that old view.
- Added one-time migration from the active V1.8.2 configuration to existing organizations.
