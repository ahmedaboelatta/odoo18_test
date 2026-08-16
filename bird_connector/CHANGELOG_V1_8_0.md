# Bird Connector 18.0.1.8.0

## Configuration
- Added **Bird Connector > Configuration > Settings** for administrators.
- Automatic connector sync with configurable interval.
- Automatic message status refresh with configurable interval.
- Automatic wallet balance refresh with configurable interval.
- Default template locale and API timeout settings.
- Manual **Clean Duplicate Templates** maintenance action.

## Template / Version cleanup
- Bird sync now keeps one canonical `bird.template` per Workspace + Project ID.
- Every Bird channel-template resource is synchronized as `bird.template.version`.
- Active/Approved version is preferred as the current template.
- Historical duplicate templates are consolidated during sync; message logs and version history are preserved.
- Template list now shows Channel, Version count and Last Sync.

## UX / Security
- Workspaces and Channels are read-only for normal internal users and maintainable by Settings administrators.
- Related Channels/Templates in Workspace are read-only lists to avoid accidental duplicate records.
- Empty channel technical fields are hidden when not populated.
- API request timeout is controlled by Bird Connector Settings.
