# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError
from dateutil.relativedelta import relativedelta
from datetime import date, datetime, time, timedelta
import io
import base64


class MonthSalaryReportWizard(models.TransientModel):
    _name = "month.salary.report.wizard"

    date_from = fields.Date(string="From", )
    date_to = fields.Date(string="To", )

    # allowance_ids = fields.Many2many('hr.allowance')

    def action_excel_wizard(self):
        data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            # 'allowance_ids': self.allowance_ids

        }
        return self.env.ref('gs_hr_payroll_report.action_month_salary_xlsx_report').report_action(self, data=data)


def create_notification(self):
    return {
        'type': 'ir.action.client',
        'tag': 'display_notification',
        'params': {
            'title': _('Warning!'),
            'message': 'Record Empty',
            'sticky': True
        }

    }


class PreparationFileXlsxReport(models.AbstractModel):
    _name = 'report.gs_hr_payroll_report.month_salary_xlsx_report'
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
        sheet.merge_range('A1:G2', 'Month Salary Report', title)
        money = workbook.add_format({'num_format': '$#,##0.00', 'bg_color': '#ffffff'})
        sheet.merge_range('A4:D4', 'From', date_style)
        sheet.merge_range('A5:D5', data.get('date_from'), date_style2)
        sheet.merge_range('E4:G4', 'To', date_style)
        sheet.merge_range('E5:G5', data.get('date_to'), date_style2)

        # Header row
        sheet.set_column(0, 0, 5)
        sheet.set_column(1, 1, 20)
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
        sheet.set_column(15, 15, 30)
        sheet.set_column(16, 16, 30)
        sheet.set_column(16, 17, 30)

        sheet.write(6, 0, 'SN', header_row_style)
        sheet.write(6, 1, 'ID', header_row_style)
        sheet.write(6, 2, 'Employee  Name', header_row_style)
        sheet.write(6, 3, 'Number of the Employee', header_row_style)
        sheet.write(6, 4, 'Batch', header_row_style)
        sheet.write(6, 5, 'From', header_row_style)
        sheet.write(6, 6, 'To', header_row_style)
        sheet.write(6, 7, 'Bank Account', header_row_style)
        sheet.write(6, 8, 'Bank  Name', header_row_style)
        sheet.write(6, 9,'Basic  Salary', header_row_style)
        sheet.write(6, 10, 'Housing Allowance', header_row_style)
        sheet.write(6, 11, 'Recurring  Allownce', header_row_style)
        sheet.write(6, 12, 'Over  Time', header_row_style)
        sheet.write(6, 13, 'Awards', header_row_style)
        sheet.write(6, 14, 'Transportation Allowance', header_row_style)
        sheet.write(6, 15,'Other Allowances', header_row_style)
        sheet.write(6, 16, 'Gross', header_row_style)
        sheet.write(6, 17, 'Penality', header_row_style)
        sheet.write(6, 18, 'GOSI', header_row_style)
        sheet.write(6, 19, 'Deduction', header_row_style)
        sheet.write(6, 20, 'loan', header_row_style)
        sheet.write(6, 21, 'Net Salary', header_row_style)

        domains = []
        if data.get('date_from') and data.get('date_to'):
            domains.append(('date_from', '>=', data.get('date_from')))
            domains.append(('date_to', '<=', data.get('date_to')))
        else:
            create_notification(self)

        preparation_file_multi = self.env['hr.payslip'].search(domains)
        row = 7
        i = 1
        total_basic = 0
        total_plenality = 0
        total_house = 0
        total_recurring = 0
        total_transport = 0
        total_other_allowance = 0
        total_award = 0
        total_over_time = 0
        total_deduction = 0
        total_insurance = 0
        total_gross_salary = 0
        total_loan_deduction = 0
        total_net_salary = 0
        for pre in preparation_file_multi:
            sheet.write(row, 0, i, date_style2)
            sheet.write(row, 1, pre.employee_id.identification_id or "", date_style2)
            sheet.write(row, 2, pre.employee_id.name or "", date_style2)
            sheet.write(row, 3, pre.employee_id.registration_number2 or "", date_style2)
            sheet.write(row, 4, pre.payslip_run_id.name or "", date_style2)
            sheet.write(row, 5, pre.date_from.strftime('%Y-%m-%d') or "", date_style2)
            sheet.write(row, 6, pre.date_to.strftime('%Y-%m-%d') or "", date_style2)
            sheet.write(row, 7, pre.employee_id.bank_account_id.acc_number or "", date_style2)
            sheet.write(row, 8, pre.employee_id.bank_account_id.bank_id.bic or "", date_style2)
            # sheet.write(row, 5, pre.employee_id.name)
            # sheet.write(row, 6, pre.employee_id.name)
            # sheet.write(row, 14, pre.payment_state, date_style2)

            for line in pre.line_ids:
                if line.code == 'BASIC':
                    sheet.write(row, 9, line.total, date_style2)
                    total_basic += line.total
                if line.code == 'HOUALLOW':
                    sheet.write(row, 10, line.total, date_style2)
                    total_house += line.total
                if line.code == 'Recurring Allownce':
                    sheet.write(row, 11, line.total, date_style2)
                    total_recurring += line.total
                if line.code == 'Over Time':
                    sheet.write(row, 12, line.total, date_style2)
                    total_over_time += line.total
                if line.code == 'PAA':
                    sheet.write(row, 13, line.total, date_style2)
                    total_award += line.total
                if line.code == 'Transportation_Allowance':
                    sheet.write(row, 14, line.total, date_style2)
                    total_transport += line.total
                if line.code == 'OTALLOW':
                    sheet.write(row, 15, line.total, date_style2)
                    total_other_allowance += line.total
                if line.code == 'GROSS':
                    sheet.write(row, 16, line.total, date_style2)
                    total_gross_salary += line.total

                if line.code == 'PAD':
                    sheet.write(row, 17, line.total, date_style2)
                    total_plenality += line.total
                if line.code == 'GOSI':
                    sheet.write(row, 18, line.total, date_style2)
                    total_insurance += line.total
                if line.code == 'DEDUCTION':
                    sheet.write(row, 19, line.total, date_style2)
                    total_deduction += line.total
                if line.code == 'loan':
                    sheet.write(row, 20, line.total, date_style2)
                    total_loan_deduction += line.total
                if line.code == 'NET':
                    sheet.write(row, 21, line.total, date_style2)
                    total_net_salary += line.total

            row += 1
            i += 1

        sheet.write(row, 8, 'المجموع', header_row_style)
        # sheet.write(row, 3, pre.payslip_run_id.name, header_row_style)
        sheet.write(row, 9, total_basic, date_style2)
        sheet.write(row, 10, total_house, date_style2)
        sheet.write(row, 11, total_recurring, date_style2)
        sheet.write(row, 12, total_over_time, date_style2)
        sheet.write(row, 13, total_award, date_style2)
        sheet.write(row, 14, total_transport, date_style2)
        sheet.write(row, 15, total_other_allowance, date_style2)
        sheet.write(row, 16, total_gross_salary, date_style2)
        sheet.write(row, 17, total_plenality, date_style2)
        sheet.write(row, 18, total_insurance, date_style2)
        sheet.write(row, 19, total_deduction, date_style2)
        sheet.write(row, 20, total_loan_deduction, date_style2)
        sheet.write(row, 21, total_net_salary, date_style2)

        for wizard in self:
            fp = io.BytesIO()
            workbook.save(fp)
            excel_file = base64.encodestring(fp.getvalue())
            wizard.leave_summary_file = excel_file
            wizard.file_name = 'Month Salary Report.xls'
            wizard.leave_report_printed = True
            fp.close()
            return {
                'view_mode': 'form',
                'res_id': wizard.id,
                'res_model': 'month.salary.report.wizard',
                'view_type': 'form',
                'type': 'ir.actions.act_window',
                'context': self.env.context,
                'target': 'new',
            }
