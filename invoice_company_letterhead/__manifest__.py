{
    'name': 'Invoice Company Letterhead',
    'version': '18.0.6.1.0',
    'summary': 'Optional company-specific PDF letterhead print action for invoices',
    'category': 'Accounting/Accounting',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['account', 'web'],
    'data': [
        'views/res_company_views.xml',
        'report/report_invoice.xml',
        'report/report_action.xml',
    ],
    'installable': True,
    'application': False,
}
