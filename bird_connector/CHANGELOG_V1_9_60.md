# Bird Connector v1.9.60

- Fixed image Copy on plain HTTP: the fallback now copies a fully rendered inline data-URL image instead of the remote image URL, avoiding blank Windows clipboard entries.
- HTTPS still uses the native binary Clipboard API when available.
- The internal Bird image clipboard remains enabled so Copy -> Paste inside the composer continues to work.
