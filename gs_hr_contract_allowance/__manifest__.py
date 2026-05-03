# -*- coding: utf-8 -*-
{
    'name': "GS HR Contract Allowance",

    'summary': """ Short (1 phrase/line) summary of the module's purpose, used as subtitle on modules listing or apps.openerp.com""",
    'description': """ Long description of module's purpose """,

    "author": "Global Solutions",
    "website": "https://globalsolutions.dev",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Human Resources/Employees',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['base', 'hr', 'hr_holidays', 'hr_contract', 'account', 'contacts', 'hr_payroll', 'gs_hr_saudi_gosi', 'gs_hr_insurance', 'l10n_sa_hr_payroll'],

    # always loaded
    'data': [
        'data/ir_sequence.xml',
        'security/ir.model.access.csv',
        'views/contract_allowance.xml',
        'views/allowances_collection.xml',
        'views/allowances.xml',
        'views/template.xml',
        'views/hr_employee_inherit.xml',
        'demo/payslip_rules.xml',
        'demo/demo.xml',
        'views/contract_duration.xml',

    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'gs_hr_contract_allowance/static/src/css/style.css',
        ],
    },
    'installable': True,
    'application': True,
}
