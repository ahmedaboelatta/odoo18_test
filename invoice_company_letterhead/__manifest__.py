{
    'name': 'Company Letterhead Reports',
    'version': '18.0.7.5.2',
    'summary': 'One company letterhead for sales, delivery, invoice and purchase reports',
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
    ],
    'installable': True,
    'application': False,
}
