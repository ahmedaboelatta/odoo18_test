{
    "name": "Hader Mobile Notifications",
    "summary": "Managed in-app notifications for Hader employees",
    "version": "1.0.0",
    "category": "Human Resources",
    "author": "Ahmed Abo EL-Atta",
    "website": "https://www.linkedin.com/in/ahmedaboelatta/",
    "support": "a7medaboelatta@gmail.com",
    "license": "LGPL-3",
    "depends": ["mail", "hader_mobile_attendance", "hader_mobile_requests"],
    "data": [
        "security/ir.model.access.csv",
        "security/push_delivery_rules.xml",
        "views/notification_views.xml",
        "data/notification_cron.xml",
    ],
    "installable": True,
}
