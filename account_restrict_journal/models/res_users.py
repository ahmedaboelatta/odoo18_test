from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    allowed_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        relation="res_users_allowed_account_journal_rel",
        column1="user_id",
        column2="journal_id",
        string="Allowed Journals",
        domain="[('company_id', 'in', company_ids)]",
        help=(
            "When Journal Restriction is enabled for this user, the user can "
            "see and use only these journals."
        ),
    )
