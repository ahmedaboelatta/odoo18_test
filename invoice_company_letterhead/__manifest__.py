{
    'name': 'Invoice Company Letterhead',
    'version': '18.0.2.0.0',
    'summary': 'Company-specific PDF invoice letterhead for multi-company environments',
    'category': 'Accounting/Accounting',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['account', 'web'],
    'data': [
        'views/res_company_views.xml',
        'report/report_invoice.xml',
    ],
    'installable': True,
    'application': False,
}
