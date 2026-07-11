# -*- coding: utf-8 -*-
{
    'name': 'Bird Connector',
    'summary': 'Bird (MessageBird) API Integration for Odoo 18',
    'version': '18.0.1.0.0',
    'category': 'Integration',
    'author': 'Ahmed Abo EL-Atta',
    'website': 'https://www.linkedin.com/in/ahmedaboelatta',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        # 1. Security files first
        'security/bird_connector_security.xml',
        'security/ir.model.access.csv',
        
        # 2. View files for backend models
        'views/bird_organization_views.xml',
        'views/bird_workspace_views.xml',
        'views/bird_channel_views.xml',
        'views/bird_contact_views.xml',
        'views/bird_conversation_views.xml',
        'views/bird_message_views.xml',
        'views/bird_template_views.xml',
        'views/bird_device_token_views.xml',
        
        # 3. Menu structures
        'views/menu_views.xml',
        
        # 4. Automation and Crons at the very end
        'data/ir_cron_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'bird_connector/static/src/js/whatsapp_preview.js',
            'bird_connector/static/src/xml/whatsapp_preview.xml',
        ],
    },
    'installable': True,
    'application': True,
}