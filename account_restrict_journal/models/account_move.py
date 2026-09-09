from odoo import _, api, models
from odoo.exceptions import AccessError


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def _journal_restriction_enabled(self):
        return self.env.user.has_group(
            "account_restrict_journal.account_restrict_journal_group_admin"
        )

    @api.model
    def _check_allowed_journal(self, journal):
        if (
            self._journal_restriction_enabled()
            and journal
            and journal.id not in self.env.user.allowed_journal_ids.ids
        ):
            raise AccessError(
                _("You are not allowed to use the journal: %s", journal.display_name)
            )

    @api.model_create_multi
    def create(self, vals_list):
        if self._journal_restriction_enabled():
            Journal = self.env["account.journal"].sudo()
            for vals in vals_list:
                if vals.get("journal_id"):
                    self._check_allowed_journal(Journal.browse(vals["journal_id"]))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("journal_id"):
            self._check_allowed_journal(
                self.env["account.journal"].sudo().browse(vals["journal_id"])
            )
        return super().write(vals)

    def action_post(self):
        for move in self:
            move._check_allowed_journal(move.journal_id)
        return super().action_post()
