# -*- coding: utf-8 -*-
{
    'name': "GS HR Payroll Custom",
    'summary': """ Payroll Custom""",
    'description': """  Payroll Custom """,
    "author": "Global Solutions",
    "website": "https://globalsolutions.dev",
    'category': 'Human Resources/Employees',
    'version': '1.0',
    # any module necessary for this one to work correctly
    'depends': ['base', 'hr_payroll', 'hr_payroll_account','gs_hr_contract_allowance'],
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/data2.xml',
        'views/payroll_inherit.xml',
        'views/hr_payroll_report.xml',
        'wizard/register_payment.xml',
    ],

    # only loaded in demonstration mode
    'installable': True,
    'application': True,
}
