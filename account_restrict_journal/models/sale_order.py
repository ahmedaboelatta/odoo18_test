from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    available_invoicing_journal_ids = fields.Many2many(
        comodel_name="account.journal",
        compute="_compute_available_invoicing_journal_ids",
        string="Available Invoicing Journals",
    )

    @api.depends("company_id")
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_available_invoicing_journal_ids(self):
        restricted = self.env.user.has_group(
            "account_restrict_journal.account_restrict_journal_group_admin"
        )
        allowed_journal_ids = set(self.env.user.allowed_journal_ids.ids)
        Journal = self.env["account.journal"].sudo()
        for order in self:
            journals = Journal.search(
                [
                    ("type", "=", "sale"),
                    ("company_id", "=", order.company_id.id),
                ]
            )
            order.available_invoicing_journal_ids = (
                journals.filtered(lambda journal: journal.id in allowed_journal_ids)
                if restricted
                else journals
            )

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

    @api.onchange("company_id")
    def _onchange_company_allowed_invoicing_journal(self):
        if (
            self.journal_id
            and self.journal_id not in self.available_invoicing_journal_ids
        ):
            self.journal_id = False

    def _prepare_invoice(self):
        self.ensure_one()
        self._check_allowed_invoicing_journal(self.journal_id)
        return super()._prepare_invoice()
