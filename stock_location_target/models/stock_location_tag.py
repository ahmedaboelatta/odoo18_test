# -*- coding: utf-8 -*-

from odoo import models, fields


class StockLocationTag(models.Model):
    _name = 'stock.location.tag'
    _description = 'Location Tags'
    _order = 'name'

    name = fields.Char(string='Tag Name', required=True)
    color = fields.Integer(string='Color Index', default=0)
    active = fields.Boolean(default=True, help="Set to false to hide the tag without deleting it.")