# -*- coding: utf-8 -*-
{
    'name': "Payments Internal Transfer",

    'summary': "This module returns the old payment internal transfer feature from old versions of V17 and older.",

    'description': """
        This module brings back the old payment internal transfer feature from old versions of Odoo 17 and older.
        It allows you to transfer payments between different payment methods (like bank transfers, wire transfers, etc.)
        from one account to another.
    """,

    'author': "TKL Smart Solutions",
    'website': "https://github.com/tklsmartsolutions",

    # for the full list
    'category': 'Accounting',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['account'],

    # always loaded
    'data': [
        'views/account_payment_view.xml',
    ],
    'images': ['static/description/thumbnail.gif'],
    'installable': True,
    'auto_install': False,
    'application': True,
    'price': 30,
    'currency':  'USD',
    'support': 'tklsmartsolutions@gmail.com',
    'license': 'LGPL-3'
}

