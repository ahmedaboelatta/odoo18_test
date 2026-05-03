# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class GsContractDurationLevel(models.Model):
    _name = 'gs.contract.duration'
    _description = 'contract Duration'

    name = fields.Char(string='Name',)