{
    'name': 'Invoice Company Letterhead',
    'version': '18.0.1.0.0',
    'summary': 'Company-specific invoice letterhead for multi-company environments',
    'category': 'Accounting/Accounting',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'views/res_company_views.xml',
        'report/report_invoice.xml',
    ],
    'installable': True,
    'application': False,
}
