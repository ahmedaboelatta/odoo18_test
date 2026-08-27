from odoo import fields, models


class CpanelMailboxTag(models.Model):
    _name = "cpanel.mailbox.tag"
    _description = "cPanel Mailbox Tag"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(default=0)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_unique", "unique(name)", "A mailbox tag with this name already exists."),
    ]
