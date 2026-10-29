{
    "name": "Alezdhar Mobile Notifications",
    "summary": "Managed in-app notifications for Alezdhar employees",
    "version": "18.0.2.1.0",
    "category": "Human Resources",
    "author": "Al-Ezdhar & Al-Rafah Trading Ltd.",
    "license": "LGPL-3",
    "depends": ["alezdhar_mobile_attendance"],
    "external_dependencies": {"python": ["firebase_admin"]},
    "data": [
        "security/notification_security.xml",
        "security/ir.model.access.csv",
        "views/notification_views.xml",
        "data/notification_cron.xml",
    ],
    "installable": True,
}
