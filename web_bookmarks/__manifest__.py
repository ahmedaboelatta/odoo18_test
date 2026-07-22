{
    "name": "Web Bookmarks",
    "version": "18.0.1.0.0",
    "summary": "Bookmark your favorite Odoo menus and external links for quick access.",
    "description": """
        This module provides a bookmark feature accessible from the navbar,
        allowing users to save quick links to Odoo menus or external websites.
    """,
    "author": "Axel Manzanilla",
    "maintainer": "Axel Manzanilla",
    "website": "https://axelmanzanilla.com",
    "license": "LGPL-3",
    "category": "Technical/Technical",
    "depends": [
        "web",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/menu_bookmark_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "web_bookmarks/static/src/components/**/*",
        ],
    },
    "auto_install": False,
}
