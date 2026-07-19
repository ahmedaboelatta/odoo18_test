# -*- coding: utf-8 -*-
{
    'name': "ZK Biotime Integration",

    'summary': "Zk Biotime Integration",
    'description': """ZK Biotime Integration""",
    'version': '1.0.0',
     'category': 'Uncategorized',
    'author': 'Cubes  Company',
    'sequence': '10',
    'website': "http://www.cubes.ly",
    'price': "150",
    'license': "OPL-1",
    "currency": "USD",
    'company': 'Cubes  Company',
    'maintainer': 'Cubes  Company',
    'support': 'odoo@cubes.info',
    'images': ['static/description/main_screenshot.png'],
    "application": True,

    'depends': ['base', 'hr', 'hr_attendance'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/biotime.xml',
        'views/terminal.xml',
        'views/employee.xml',
        'data/menuitems.xml',
        'data/cron.xml'
    ]

}
