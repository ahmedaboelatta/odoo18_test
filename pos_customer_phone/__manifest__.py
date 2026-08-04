{
    "name": "POS Customer Phone",
    "summary": "Capture, normalize, and search customer phone numbers on POS orders without creating partners.",
    "author": "Custom",
    "website": "https://example.com",
    "category": "Point of Sale",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_customer_phone/static/src/js/pos_phone_popup.js",
            "pos_customer_phone/static/src/js/screens.js",
            "pos_customer_phone/static/src/xml/screens.xml",
            "pos_customer_phone/static/src/scss/screens.scss",
        ],
    },
}
