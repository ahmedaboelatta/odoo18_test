{
    "name": "User Tags",
    "summary": "Add colored tags to users",
    "version": "18.0.1.0.0",
    "category": "Settings/Users & Companies",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_users_tag_views.xml",
        "views/res_users_views.xml",
    ],
    "installable": True,
    "application": False,
}
