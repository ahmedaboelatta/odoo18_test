# -*- coding: utf-8 -*-
# Copyright 2019 Coop IT Easy SCRL fs
#   Robin Keunen <robin@coopiteasy.be>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _


class Allowances(models.Model):
    _name = 'hr.allowance'
    _description = 'Allowances'

    name = fields.Char('Allowance')

    @api.model
    def create(self, vals):
        res = super(Allowances, self).create(vals)
        res.action_create_allowances_collect()
        return res

    def action_create_allowances_collect(self):
        for rec in self:
            self.env["allowances.collect"].create({"name": rec.name})