# -*- coding: utf-8 -*-
{
    'name': "Vacation settlement for Employee",
    'summary': """ This workflow automates the process of settling vacation leave for employees.
        It guides them through the steps of requesting and approving their vacation,
        and calculates the appropriate compensation based on their remaining leave balance
        and company policies. """,
    'description': """  This workflow automates vacation leave settlement for employees, 
     including request submission, approval, calculations, and document generation. """,
    'author': "Global Solutions",
    'contributors': [
       'Mohamed Abdalla <mohamedabdalla142001@gmail.com>',
    ],
    'website': "www.https://www.globalsolutions.dev/",
    'version': '1.0',
    'category': 'Human Resources',
    'depends': ['hr','gs_hr_insurance','gs_hr_contract_allowance','account','gs_time_off_custom'],
    'data': [
        'security/ir.model.access.csv',
        'data/employee_vacation_settlement_data.xml',
        'views/hr_vacation_settlement.xml',
        'views/type_allowances_setting.xml',
        'report/custom_header_footer.xml',
        'report/report_vacation.xml',
        'report/report.xml',
    ],
    'license': 'OPL-1',
    "pre_init_hook": None,
    "post_init_hook": None,
}
