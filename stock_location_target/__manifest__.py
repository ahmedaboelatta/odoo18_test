# -*- coding: utf-8 -*-

{
    'name': 'Stock Location Expected Goods Cost',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Add Expected Goods Cost field to stock locations',
    'description': """
This module adds an "Expected Goods Cost" financial target field to each warehouse location.
The target represents the Expected Goods Cost (Target Cost) for that specific location.
    """,
    'author': 'Ahmed Abo EL-Atta',
    'website': 'https://alezdhar.com/',
    'depends': ['base', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_location_views.xml',
    ],
    'demo': [],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
