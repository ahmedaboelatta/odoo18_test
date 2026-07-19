   # -*- coding: utf-8 -*-
import logging
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import requests, json


class BioTimeEmployee(models.Model):
    _name = 'biotime.employee'

    name = fields.Char(string="Name")
    emp_code = fields.Char(string="Employee Code")
    employee_id = fields.Char(string="Employee ID")
    odoo_employee_id = fields.Many2one('hr.employee', string="Odoo Employee")
    biotime_id = fields.Many2one('biotime.config', string="Biotime")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.company.id)


    # @api.constrains('odoo_employee_id')
    # def check_validate_odoo_employee_id(self):
    #     for rec in self:
    #         search = self.sudo().search([
    #             ('odoo_employee_id','=', rec.odoo_employee_id.id),
    #             ('id','!=', rec.id),
    #         ])
    #         if search:
    #             raise ValidationError(_("You can't set odoo employee in more than one record"))