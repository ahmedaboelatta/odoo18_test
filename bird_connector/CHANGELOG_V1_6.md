# V1.6.0

- Rebuilt the WhatsApp preview to closely mirror Bird's 320px preview structure.
- Restored the Sync Template action on submitted/synced templates.
- Added Body variable insertion (`{{1}}`, `{{2}}`, ...), variable metadata and sample values.
- Added variable types: User Name, User Mobile, Free Text, Portal Link and Field of Model.
- Send wizard now uses the variable technical key and prefills mapped values where possible.
- Restored wallet balance refresh using the documented MessageBird Balance API.
- Added optional separate Balance API Access Key for accounts where the Bird Platform key is not accepted by the legacy balance endpoint.
