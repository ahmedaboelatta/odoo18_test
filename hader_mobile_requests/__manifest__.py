{
    "name": "Hader Mobile Requests",
    "summary": "Time off and extensible employee service requests for Hader Mobile",
    "version": "1.0.0",
    "category": "Human Resources",
    "author": "Ahmed Abo EL-Atta",
    "website": "https://www.linkedin.com/in/ahmedaboelatta/",
    "support": "a7medaboelatta@gmail.com",
    "license": "LGPL-3",
    "depends": ["hader_mobile_core", "hr_holidays", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/service_data.xml",
        "views/service_request_views.xml",
    ],
    "installable": True,
}
