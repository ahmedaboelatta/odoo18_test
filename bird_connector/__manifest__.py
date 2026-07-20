{
    "name": "Bird Connector",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "summary": "Integrate Odoo with Bird.com API for WhatsApp messaging",
    "description": """
Bird Connector
==============

Manage Bird organizations, workspaces, channels, WhatsApp templates, and message logs directly from Odoo 18.

Features:
* Configure Bird API credentials (AccessKey + Workspace ID)
* Manage Organizations and test API connectivity
* Manage Workspaces and Channels (WhatsApp, Email, etc.)
* Sync and preview WhatsApp templates with dynamic variables
* Send WhatsApp template messages via API engine
* Log sent messages with status tracking
    """,
    "author": "Your Company",
    "website": "https://www.yourcompany.com",
    "license": "LGPL-3",
    "depends": ["base", "mail", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/bird_organization_views.xml",
        "views/bird_workspace_views.xml",
        "views/bird_channel_views.xml",
        "views/bird_template_views.xml",
        "views/bird_message_log_views.xml",
        "views/bird_connector_menu.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
