{
    "name": "Bird Connector",
    "version": "18.0.1.8.1",
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
* Create WhatsApp templates locally in Odoo
* Submit templates to Bird / Meta and track approval status
* Send only approved WhatsApp templates
* Refresh delivery status manually or automatically
* Retry failed messages with full request/response audit logs
* Persistent Configuration list/form for automatic sync, wallet refresh and message status jobs
* Canonical one-template-per-project synchronization with Bird Versions history
    """,
    "author": "Your Company",
    "website": "https://www.yourcompany.com",
    "license": "LGPL-3",
    "depends": ["base", "mail", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "data/bird_configuration_data.xml",
        "views/res_config_settings_views.xml",
        "views/bird_configuration_views.xml",
        "views/bird_organization_views.xml",
        "views/bird_workspace_views.xml",
        "views/bird_channel_views.xml",
        "views/bird_template_views.xml",
        "views/bird_message_log_views.xml",
        "wizard/bird_send_message_wizard_views.xml",
        "views/bird_connector_menu.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
