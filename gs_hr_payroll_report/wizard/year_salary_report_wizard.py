# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError
from dateutil.relativedelta import relativedelta
from datetime import date, datetime, time, timedelta
import io
import base64


class YearSalaryReportWizard(models.TransientModel):
    _name = "year.salary.report.wizard"

    employee_ids = fields.Many2many('hr.employee')
    date_from = fields.Date(string="From", )
    date_to = fields.Date(string="To", )

    select_year = fields.Selection([(str(x), str(x)) for x in range(2020, 2040)], string='Select Year', tracking=True)

    def action_excel_wizard(self):
        data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'employee_ids': self.employee_ids.ids,
            'select_year': self.select_year,

        }
        return self.env.ref('gs_hr_payroll_report.action_year_salary_xlsx_report').report_action(self, data=data)

    @api.onchange('select_year')
    def select_year_func(self):
        if self.select_year:
            self.date_from = date(int(self.select_year), 1, 1)
            self.date_to = date(int(self.select_year), 12, 31)


class PreparationFileXlsxReport(models.AbstractModel):
    _name = 'report.gs_hr_payroll_report.year_salary_xlsx_report'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, partners):
        sheet = workbook.add_worksheet('')
        bold = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#fffbed', 'border': True})
        title = workbook.add_format(
            {'bold': True, 'align': 'center', 'font_size': 20, 'bg_color': '#f2f2f2', 'border': True})
        date_style = workbook.add_format(
            {'bold': True, 'align': 'center', 'font_size': 14, 'bg_color': '#f2f2f2', 'border': True})
        date_style2 = workbook.add_format({'align': 'center', 'font_size': 12})
        header_row_style = workbook.add_format(
            {'bg_color': '#f2f2f2', 'color': '#000000', 'bold': True, 'align': 'center', 'border': True})
        sheet.merge_range('A1:G2', 'Year Salary Report', title)
        money = workbook.add_format({'num_format': '$#,##0.00', 'bg_color': '#ffffff'})
        # sheet.merge_range('A4:D4', 'From', date_style)
        # sheet.merge_range('A5:D5', data.get('date_from'), date_style2)
        # sheet.merge_range('E4:G4', 'To', date_style)
        # sheet.merge_range('E5:G5', data.get('date_to'), date_style2)

        # Header row
        sheet.set_column(0, 0, 5)
        sheet.set_column(1, 1, 30)
        sheet.set_column(2, 2, 50)
        sheet.set_column(3, 3, 30)
        sheet.set_column(4, 4, 30)
        sheet.set_column(5, 5, 30)
        sheet.set_column(6, 6, 30)
        sheet.set_column(7, 7, 30)
        sheet.set_column(8, 8, 30)
        sheet.set_column(9, 9, 30)
        sheet.set_column(10, 10, 30)
        sheet.set_column(11, 11, 30)
        sheet.set_column(12, 12, 30)
        sheet.set_column(13, 13, 30)
        sheet.set_column(14, 14, 30)
        sheet.set_column(14, 15, 30)

        sheet.write(6, 0, 'رقم', header_row_style)
        sheet.write(6, 1, 'أي دي', header_row_style)
        sheet.write(6, 2, 'أسم الموظف', header_row_style)
        sheet.write(6, 3, 'رقم تسجيل الموظف', header_row_style)
        sheet.write(6, 4, 'أسم الدفعة', header_row_style)
        sheet.write(6, 5, 'الراتب الأساسي', header_row_style)
        sheet.write(6, 6, 'بدل السكن', header_row_style)
        sheet.write(6, 7, 'بدل النقل', header_row_style)
        # sheet.write(6, 8, 'بدل أتصال', header_row_style)
        # sheet.write(6, 9, 'طبيعة عمل', header_row_style)
        sheet.write(6, 8, 'بدلات أخري', header_row_style)
        sheet.write(6, 9, 'إضافات', header_row_style)
        sheet.write(6, 10, 'أستقطاعات', header_row_style)
        sheet.write(6, 11, 'أستقطاعات التأمينات الأجتماعية', header_row_style)
        sheet.write(6, 12, 'الصافي', header_row_style)
        # sheet.write(6, 13, 'تاريخ الدفع', header_row_style)

        domains = []
        if data.get('employee_ids'):
            employee_ids = data.get('employee_ids')
            domains.append(('employee_id', 'in', employee_ids))

        if data.get('date_from') and data.get('date_to'):
            domains.append(('date_from', '>=', data.get('date_from')))
            domains.append(('date_to', '<=', data.get('date_to')))

        preparation_file_multi = self.env['hr.payslip'].search(domains)
        row = 7
        i = 0
        total_basic = 0
        total_house = 0
        total_transport = 0
        total_other_allowance = 0
        total_award = 0
        total_deduction = 0
        total_insurance = 0
        total_salary = 0
        for pre in preparation_file_multi:
            print('pre.employee_id.name', pre.employee_id.name)

            sheet.write(row, 0, i, date_style2)
            sheet.write(row, 1, pre.employee_id.identification_id, date_style2)
            sheet.write(row, 2, pre.employee_id.name, date_style2)
            sheet.write(row, 3, pre.employee_id.registration_number2, date_style2)
            sheet.write(row, 4, pre.payslip_run_id.name, date_style2)
            # sheet.write(row, 5, pre.employee_id.name)
            # sheet.write(row, 6, pre.employee_id.name)
            # sheet.write(row, 12, pre.payment_state)

            for line in pre.line_ids:
                if line.code == 'BASIC':
                    sheet.write(row, 5, line.total, date_style2)
                    total_basic += line.total
                if line.name == 'House Allowance':
                    sheet.write(row, 6, line.total, date_style2)
                    total_house += line.total
                if line.name == 'Transportation Allowance':
                    sheet.write(row, 7, line.total, date_style2)
                    total_transport += line.total
                if line.name == 'Other Allowance':
                    sheet.write(row, 8, line.total, date_style2)
                    total_other_allowance += line.total
                if line.name == 'Penalties & Awards Awards':
                    sheet.write(row, 9, line.total, date_style2)
                    total_award += line.total
                if line.name == 'Deduction Loan':
                    sheet.write(row, 10, line.total, date_style2)
                    total_deduction += line.total
                if line.name == 'GOSI':
                    sheet.write(row, 11, line.total, date_style2)
                    total_insurance += line.total
                if line.name == 'صافي المرتب':
                    sheet.write(row, 12, line.total, date_style2)
                    total_salary += line.total

            row += 1
            i += 1

        sheet.write(row, 4, 'المجموع', header_row_style)
        # sheet.write(row, 1, pre.payslip_run_id.name, header_row_style)
        sheet.write(row, 5, total_basic, date_style2)
        sheet.write(row, 6, total_house, date_style2)
        sheet.write(row, 7, total_transport, date_style2)
        sheet.write(row, 8, total_other_allowance, date_style2)
        sheet.write(row, 9, total_award, date_style2)
        sheet.write(row, 10, total_deduction, date_style2)
        sheet.write(row, 11, total_insurance, date_style2)
        sheet.write(row, 12, total_salary, date_style2)

        for wizard in self:
            fp = io.BytesIO()
            workbook.save(fp)
            excel_file = base64.encodestring(fp.getvalue())
            wizard.leave_summary_file = excel_file
            wizard.file_name = 'Year Salary Report.xls'
            wizard.leave_report_printed = True
            fp.close()
            return {
                'view_mode': 'form',
                'res_id': wizard.id,
                'res_model': 'year.salary.report.wizard',
                'view_type': 'form',
                'type': 'ir.actions.act_window',
                'context': self.env.context,
                'target': 'new',
            }
