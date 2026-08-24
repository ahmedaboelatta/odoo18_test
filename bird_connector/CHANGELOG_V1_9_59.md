# Bird Connector v1.9.59

- Copy on image now first uses a synchronous legacy browser copy path on the rendered image, allowing a real OS clipboard copy even when Odoo is opened over plain HTTP where possible.
- Native Clipboard API remains preferred on HTTPS and the internal Bird clipboard remains as fallback.
- Message action menu is rendered at inbox-root level so it is no longer trapped behind the conversation sidebar stacking context.
