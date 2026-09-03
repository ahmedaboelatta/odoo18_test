{
    'name': 'Company Letterhead Reports',
    'version': '18.0.7.7.7',
    'summary': 'One company letterhead for sales, delivery, invoice, purchase and payment vouchers',
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
    ],
    'installable': True,
    'application': False,
}
