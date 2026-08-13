{
    "name": "POS Customer Attachments",
    "version": "18.0.1.1.0",
    "category": "Point of Sale",
    "summary": "Customer-driven attachment requirements and audit controls for POS orders",
    "description": """
POS Customer Attachments
========================
Adds a customer-level policy that marks future POS orders as requiring attachments.

Main features:
- Require POS attachments per customer.
- Minimum required attachment count.
- Requirement snapshot on each POS order at creation time.
- Conditional POS order attachment smart button.
- Attachment counter and compliance status.
- Ready-made filters for required / with attachments / missing attachments.
- Chatter audit log when attachments are uploaded or deleted.
- Optional automatic image filename normalization.
- No modification of Odoo core or Enterprise source code.
    """,
    "author": "Ahmed Abo EL-Atta",
    'website': 'https://alezdhar.com',
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
        "views/pos_order_attachment_upload_wizard_views.xml",
        "views/pos_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
