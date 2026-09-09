from odoo import _, api, models
from odoo.exceptions import AccessError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.model
    def _deny_management_for_restricted_user(self):
        if self.env.user.has_group(
            "account_restrict_journal.account_restrict_journal_group_admin"
        ):
            raise AccessError(
                _("Restricted journal users cannot create, edit, or delete journals.")
            )

    @api.model_create_multi
    def create(self, vals_list):
        self._deny_management_for_restricted_user()
        return super().create(vals_list)

    def write(self, vals):
        self._deny_management_for_restricted_user()
        return super().write(vals)

    def unlink(self):
        self._deny_management_for_restricted_user()
        return super().unlink()

