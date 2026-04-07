# -*- coding: utf-8 -*-
{
    'name': "Zkteco Biopro 8.5 SA40 Attendance",
    'summary': """
        Integrate Zkteco BioPro SA40 with attendances app via BioTime 8.5 API
    """,
    'author': "Odoo PS",
    'website': "https://www.odoo.com",
    "version": "18.0.0.1.0",
    'license': 'OEEL-1',
    'depends': ['hr_attendance'],
    'data': [
        'security/ir.model.access.csv',
        'views/biotime_server_views.xml',
        'views/hr_employee.xml',
        'views/hr_views.xml',
        'data/ir_cron_data.xml',
    ],
}
