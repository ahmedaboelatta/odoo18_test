{
    'name': 'Company Letterhead Reports',
    'version': '18.0.7.9.0',
    'summary': 'Portrait and landscape company letterheads for business and accounting reports',
    'category': 'Accounting/Accounting',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': [
        'account', 'web', 'sale_management', 'stock', 'purchase',
        'custom_invoice_report',
    ],
    'data': [
        'views/res_company_views.xml',
        'report/report_invoice.xml',
        'report/report_action.xml',
        'views/account_payment_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
}
