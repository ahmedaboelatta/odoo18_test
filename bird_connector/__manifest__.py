{
    "name": "Bird Connector",
    "version": "18.0.1.9.55",
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
* Real-time WhatsApp webhook subscriptions for inbound/outbound/interaction events
* Signed webhook verification and webhook event audit log
* Separate Bird Contacts with multi-tag classification and inbound auto-upsert
* Bird Conversations with inbound history, unread tracking, contact smart button and direct text replies
* Smart phone search, contact tag colors, Teams / Queues, auto-routing, queued bulk template sending and team-scoped assignment
* Campaign analytics with delivery/failure rates, failure-code analysis and retryable-recipient drill-down
* Persistent Configuration list/form for automatic sync, wallet refresh and message status jobs
* Canonical one-template-per-project synchronization with Bird Versions history
    """,
    "author": "Your Company",
    "website": "https://www.yourcompany.com",
    "license": "LGPL-3",
    "depends": ["base", "mail", "web", "bus"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "data/bird_organization_configuration_migration.xml",
        "views/bird_organization_views.xml",
        "views/bird_workspace_views.xml",
        "views/bird_channel_views.xml",
        "views/bird_contact_views.xml",
        "views/bird_conversation_views.xml",
        "views/bird_team_views.xml",
        "views/bird_routing_views.xml",
        "views/bird_quick_reply_views.xml",
        "views/bird_bulk_send_views.xml",
        "views/bird_template_views.xml",
        "views/bird_message_log_views.xml",
        "views/bird_webhook_views.xml",
        "wizard/bird_send_message_wizard_views.xml",
        "views/bird_connector_menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "bird_connector/static/src/scss/bird_conversation.scss",
            "bird_connector/static/src/js/bird_inbox.js",
            "bird_connector/static/src/js/bird_realtime.js",
            "bird_connector/static/src/js/bird_campaign_dashboard.js",
            "bird_connector/static/src/xml/bird_inbox.xml",
            "bird_connector/static/src/xml/bird_campaign_dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
