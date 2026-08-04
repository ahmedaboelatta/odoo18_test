{
    'name': 'POS Customer Phone',
    'version': '1.0.0',
    'category': 'Point of Sale',
    'summary': 'Capture walk-in customer phone in POS without creating partner',
    'depends': ['point_of_sale'],
    'data': [
        'views/pos_order_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_customer_phone/static/src/xml/screens.xml',
            'pos_customer_phone/static/src/js/pos_phone_popup.js',
            'pos_customer_phone/static/src/js/screens.js',
            'pos_customer_phone/static/src/scss/screens.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}