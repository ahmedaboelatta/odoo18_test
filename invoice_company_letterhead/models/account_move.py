from odoo import models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _get_letterhead_analytic_distribution(self):
        """Format analytic distribution keys as readable account names."""
        self.ensure_one()
        result = []
        for account_keys, percentage in (self.analytic_distribution or {}).items():
            try:
                account_ids = [int(value) for value in account_keys.split(',') if value]
            except (TypeError, ValueError):
                account_ids = []
            accounts = self.env['account.analytic.account'].browse(account_ids).exists()
            label = ', '.join(accounts.mapped('display_name')) or account_keys
            result.append('%s: %g%%' % (label, percentage))
        return '; '.join(result)
