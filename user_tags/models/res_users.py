from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    user_tag_ids = fields.Many2many(
        comodel_name="res.users.tag",
        relation="res_users_tag_rel",
        column1="user_id",
        column2="tag_id",
        string="Tags",
    )
