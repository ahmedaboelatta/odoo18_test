# v1.9.81

- Fix HTTP 422 when updating an existing Bird contact by sending `displayName` inside `attributes`, as required by Bird's PATCH contact schema.
- Keep the required top-level `displayName` format for new contact creation.
- Surface additional Bird validation response details so any future malformed field is identifiable from Odoo.
