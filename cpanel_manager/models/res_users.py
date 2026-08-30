from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    cpanel_restrict_by_tags = fields.Boolean(
        string="Restrict cPanel Mailboxes by Tags",
        help="When enabled, the user can only see cPanel mailboxes carrying one of the allowed tags.",
    )
    cpanel_mailbox_tag_ids = fields.Many2many(
        "cpanel.mailbox.tag",
        "res_users_cpanel_mailbox_tag_rel",
        "user_id",
        "tag_id",
        string="Allowed cPanel Mailbox Tags",
    )
