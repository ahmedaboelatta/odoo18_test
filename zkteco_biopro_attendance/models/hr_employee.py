from odoo import _, models, fields
from odoo.exceptions import UserError
from .tools import batch


class HrEmployeeBase(models.AbstractModel):
    _inherit = 'hr.employee.base'

    zk_emp_code = fields.Char()
    zk_emp_id = fields.Integer()


class HrEmployeePrivate(models.Model):
    _inherit = 'hr.employee'


    def sync_with_server(self):
        odoo_employee_ids = self.env['hr.employee'].search([('zk_emp_code', '!=', False), ('zk_emp_id', '=', False)])

        if not odoo_employee_ids:
            return UserError('There are no Odoo employees that currently need to be synchronized with ZKTeco.')

        server = self.env['biotime.server'].search([])

        if not server:
            raise UserError(_('No Biotime Server configured.'))

        server.get_jwt_token(raise_alert=False)

        employee_list = server._get_asset_from_server(asset_type='employee')
        biotime_employee_code_set = {e.get('emp_code'): e.get('id') for e in employee_list}

        for employee_batch in batch(odoo_employee_ids):
            for employee in employee_batch:
                if biotime_employee_code_set.get(employee.zk_emp_code):
                    employee.zk_emp_id = biotime_employee_code_set[employee.zk_emp_code]
            self._cr.commit()

        to_add_to_biotime_set = odoo_employee_ids.filtered(lambda r: r.zk_emp_code not in biotime_employee_code_set)
        if to_add_to_biotime_set:
            server._add_to_biotime_server(to_add_to_biotime_set)
