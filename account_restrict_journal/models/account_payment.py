from odoo import _, api, models
from odoo.exceptions import AccessError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    @api.model
    def _check_allowed_payment_journal(self, journal):
        if (
            self.env.user.has_journal_restriction()
            and journal
            and journal.id not in self.env.user.allowed_journal_ids.ids
        ):
            raise AccessError(
                _("You are not allowed to use the journal: %s", journal.display_name)
            )

    @api.model_create_multi
    def create(self, vals_list):
        Journal = self.env["account.journal"].sudo()
        for vals in vals_list:
            if vals.get("journal_id"):
                self._check_allowed_payment_journal(Journal.browse(vals["journal_id"]))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("journal_id"):
            self._check_allowed_payment_journal(
                self.env["account.journal"].sudo().browse(vals["journal_id"])
            )
        return super().write(vals)
