from odoo import api, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    @api.model
    def _get_batch_available_journals(self, batch_result):
        journals = super()._get_batch_available_journals(batch_result)
        if self.env.user.has_group(
            "account_restrict_journal.account_restrict_journal_group_admin"
        ):
            journals &= self.env.user.allowed_journal_ids
        return journals
