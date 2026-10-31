{
    "name": "Alezdhar Mobile Requests",
    "summary": "Time off and extensible employee service requests for Alezdhar Mobile",
    "version": "18.0.5.0.0",
    "category": "Human Resources",
    "author": "Al-Ezdhar & Al-Rafah Trading Ltd.",
    "license": "LGPL-3",
    "depends": ["alezdhar_mobile_core", "hr_holidays", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/service_data.xml",
        "views/service_request_views.xml",
    ],
    "installable": True,
}
