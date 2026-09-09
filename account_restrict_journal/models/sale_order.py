from odoo import _, api, models
from odoo.exceptions import AccessError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def _check_allowed_invoicing_journal(self, journal):
        user = self.env.user
        if (
            user.has_group(
                "account_restrict_journal.account_restrict_journal_group_admin"
            )
            and journal
            and journal.id not in user.allowed_journal_ids.ids
        ):
            raise AccessError(
                _("You are not allowed to use the invoicing journal: %s", journal.display_name)
            )

    @api.model_create_multi
    def create(self, vals_list):
        Journal = self.env["account.journal"].sudo()
        for vals in vals_list:
            if vals.get("journal_id"):
                self._check_allowed_invoicing_journal(
                    Journal.browse(vals["journal_id"])
                )
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("journal_id"):
            self._check_allowed_invoicing_journal(
                self.env["account.journal"].sudo().browse(vals["journal_id"])
            )
        return super().write(vals)

    def _prepare_invoice(self):
        self.ensure_one()
        self._check_allowed_invoicing_journal(self.journal_id)
        return super()._prepare_invoice()

