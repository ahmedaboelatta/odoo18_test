from odoo import _, fields, models
from odoo.exceptions import UserError


class AlezdharMobileAudit(models.Model):
    _name = "alezdhar.mobile.audit"
    _description = "Alezdhar Mobile Audit"
    _order = "create_date desc, id desc"

    identity_id = fields.Many2one(
        "alezdhar.mobile.identity", index=True, ondelete="set null", readonly=True
    )
    company_id = fields.Many2one("res.company", required=True, index=True, readonly=True)
    event_type = fields.Char(required=True, index=True, readonly=True)
    request_id = fields.Char(index=True, readonly=True)
    outcome = fields.Selection(
        [("success", "Success"), ("denied", "Denied"), ("error", "Error")],
        required=True,
        readonly=True,
    )
    metadata_json = fields.Text(readonly=True)

    def write(self, vals):
        raise UserError(_("Mobile audit records are immutable."))

    def unlink(self):
        raise UserError(_("Mobile audit records are immutable."))

