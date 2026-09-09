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

    # Upgrade compatibility: the 18.0.1.0.0 user view referenced journal_ids.
    # Keep a writable alias until that stored view is replaced during upgrade.
    journal_ids = fields.Many2many(
        related="allowed_journal_ids",
        string="Allowed Journals (Legacy)",
        readonly=False,
    )
