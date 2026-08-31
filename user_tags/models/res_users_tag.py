from odoo import fields, models


class ResUsersTag(models.Model):
    _name = "res.users.tag"
    _description = "User Tag"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(string="Color")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "A user tag with this name already exists."),
    ]
