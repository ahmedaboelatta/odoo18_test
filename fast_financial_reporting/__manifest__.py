{
    "name": "Fast Financial Reporting",
    "version": "18.0.0.1.0",
    "category": "Accounting/Accounting",
    "summary": "Fast summarized financial reporting for large Odoo accounting databases",
    "description": """Initial safe skeleton. Creates only empty custom reporting/configuration tables and UI. It does not scan account.move.line and does not start background aggregation.""",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["account", "analytic"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/financial_daily_summary_views.xml",
        "views/financial_monthly_summary_views.xml",
        "views/financial_sync_state_views.xml",
        "views/financial_report_config_views.xml",
        "views/menus.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
