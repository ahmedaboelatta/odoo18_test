# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    vacation_journal_id = fields.Many2one(
        "account.journal",
        string="Default Vacation Journal",
        check_company=True,
        domain="[('type', '=', 'Miscellaneous'), ('company_id', '=', company_id)]",
        help="The company's default journal used when an employee vacation is created.",
    )
    company_vacation_journal_id = fields.Many2one(
        "account.journal",
        string="Default Company Vacation Journal",
        check_company=True,
        domain="[('type', 'in', ['cash', 'bank']), ('company_id', '=', company_id)]",
        help="The company's default journal used when a company vacation is created.",
    )
