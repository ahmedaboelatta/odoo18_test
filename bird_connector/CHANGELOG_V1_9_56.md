# v1.9.56

- Replaced separate Copy / Copy image actions with one context-aware **Copy** action.
- Prevented the Odoo client crash when `navigator.clipboard` is unavailable on HTTP.
- Added text-copy fallback and best-effort image-copy fallback for non-secure browser contexts.
- Raised message action menu stacking so it stays above the conversation sidebar/list.
- Stopped using the uploaded image filename as Bird `altText`, preventing the filename from appearing below sent WhatsApp images.
