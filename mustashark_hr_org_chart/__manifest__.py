{
    "name": "HR Org Chart Interactive",
    "version": "18.1.0.0",
    "summary": "Interactive organizational chart for employees and departments",
    "description": """
Interactive Organizational Chart
================================
A clear, visual org chart built on the employee manager hierarchy
(hr.employee parent_id) and the department tree (hr.department).

Features
--------
* Employee org chart with photos, job titles and departments
* Department tree view (managers + headcount)
* Filter by department (managers chain is kept so the tree stays connected)
* Search by name / job title, with auto-expand to matches
* Expand / collapse branches, pan & zoom, fit to screen
* Click an employee to see details (manager, direct reports, contacts)
* Double-click to open the employee / department form
* Print friendly

Only public directory fields are exposed (name, job, department, manager,
work email/phone, photo). No salary or private HR data is used.
""",
    "author": "Muse",
    "category": "Human Resources",
    "depends": ["hr"],
    "data": [
        "views/mustashark_hr_org_chart_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mustashark_hr_org_chart/static/src/mustashark_org_chart/org_chart.js",
            "mustashark_hr_org_chart/static/src/mustashark_org_chart/org_chart.xml",
            "mustashark_hr_org_chart/static/src/mustashark_org_chart/org_chart.scss",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
