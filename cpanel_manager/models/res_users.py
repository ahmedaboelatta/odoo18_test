from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    cpanel_mailbox_tag_ids = fields.Many2many(
        "cpanel.mailbox.tag",
        "res_users_cpanel_mailbox_tag_rel",
        "user_id",
        "tag_id",
        string="Allowed cPanel Mailbox Tags",
        help="Leave empty for unrestricted access. Select tags to restrict the user to matching mailboxes.",
    )
