# Bird Connector 18.0.1.4.2

## Fixed
- Replaced the invalid combined Touchpoints endpoint with Bird Support's documented staged flow.
- Project creation now uses `POST /workspaces/{workspaceId}/projects`.
- Channel Template creation now uses `POST /workspaces/{workspaceId}/projects/{projectId}/channel-templates`.
- Activation still uses the project-scoped Channel Template activate endpoint.
- Corrected WhatsApp deployment key to `whatsappCategory` and added the required platform metadata.
- Moved `channelGroupIds` into WhatsApp `platformContent`, matching the current Touchpoints template model.
- Added full request/response audit data for each submit stage.
- Retry safety: if Project creation succeeds but Channel Template creation fails, the saved Project ID is reused.

## Existing fixes retained
- Persistent WhatsApp preview after Save/Edit.
- Approved-only template sending.
- Message delivery tracking and logs.
