from odoo import fields, models


class CpanelOperationLog(models.Model):
    _name = "cpanel.operation.log"
    _description = "cPanel Operation Log"
    _order = "create_date desc"

    server_id = fields.Many2one("cpanel.server", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="server_id.company_id", store=True, index=True)
    mailbox_id = fields.Many2one("cpanel.mailbox", ondelete="set null", index=True)
    operation = fields.Char(required=True, index=True)
    success = fields.Boolean(default=True, index=True)
    message = fields.Text()
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
