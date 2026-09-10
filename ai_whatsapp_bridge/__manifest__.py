{
    "name": "AI WhatsApp Bridge",
    "version": "18.0.1.0.0",
    "category": "Productivity/Discuss",
    "summary": "Route inbound Bird WhatsApp messages to brand-specific AI workflows",
    "license": "LGPL-3",
    "depends": ["bird_connector"],
    "data": [
        "security/ir.model.access.csv",
        "views/ai_whatsapp_profile_views.xml",
        "views/ai_forward_log_views.xml",
        "views/res_config_settings_views.xml",
        "views/ai_whatsapp_menu.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
