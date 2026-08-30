# v1.9.82

- Fix Bird contact synchronization for workspaces whose standard Country attribute key is `country`.
- Stop sending the undefined `countryCode` key that caused HTTP 422 attribute-definition errors.
- Continue sending the selected country's ISO code, such as `SA`, to Bird's Country attribute.
