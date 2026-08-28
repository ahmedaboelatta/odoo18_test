from odoo import api, fields, models, _
from odoo.exceptions import UserError


class InvoicePrintWizard(models.TransientModel):
    _name = 'invoice.print.wizard'
    _description = 'Invoice Preview and Print'

    move_id = fields.Many2one('account.move', string='Invoice', readonly=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    design_id = fields.Many2one(
        'invoice.letterhead.design', string='Design', required=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    preview_mode = fields.Boolean(compute='_compute_preview_mode')

    @api.depends('move_id')
    def _compute_preview_mode(self):
        for wizard in self:
            wizard.preview_mode = not wizard.move_id

    def _report_data(self):
        self.ensure_one()
        return {'design_id': self.design_id.id, 'sample': not bool(self.move_id)}

    def action_preview(self):
        self.ensure_one()
        if not self.design_id:
            raise UserError(_('Please select an invoice design.'))
        action = self.env.ref('invoice_company_letterhead.action_report_invoice_design_preview')
        return action.report_action(self, data=self._report_data())

    def action_print(self):
        self.ensure_one()
        if not self.move_id:
            return self.action_preview()
        action = self.env.ref('invoice_company_letterhead.action_report_invoice_letterhead')
        return action.with_context(letterhead_design_id=self.design_id.id).report_action(
            self.move_id, data=self._report_data()
        )
