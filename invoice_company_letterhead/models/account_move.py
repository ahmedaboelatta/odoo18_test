from odoo import models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _get_letterhead_analytic_distribution(self):
        """Show analytic account names and percentages instead of JSON IDs."""
        self.ensure_one()
        values = []
        for analytic_keys, percentage in (self.analytic_distribution or {}).items():
            try:
                account_ids = [
                    int(account_id)
                    for account_id in str(analytic_keys).split(',')
                    if account_id
                ]
            except ValueError:
                account_ids = []
            accounts = self.env['account.analytic.account'].browse(account_ids).exists()
            account_names = ', '.join(accounts.mapped('display_name'))
            label = account_names or str(analytic_keys)
            values.append('%s: %g%%' % (label, percentage))
        return '; '.join(values)
