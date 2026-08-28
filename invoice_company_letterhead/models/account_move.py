from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_open_invoice_print_wizard(self):
        self.ensure_one()
        default_design = self.env['invoice.letterhead.design'].search([
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
            ('is_default', '=', True),
        ], limit=1)
        if not default_design:
            default_design = self.env['invoice.letterhead.design'].search([
                ('company_id', '=', self.company_id.id), ('active', '=', True),
            ], limit=1)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Preview / Print Invoice',
            'res_model': 'invoice.print.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'default_company_id': self.company_id.id,
                'default_design_id': default_design.id,
            },
        }
