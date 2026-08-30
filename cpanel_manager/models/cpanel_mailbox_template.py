from odoo import fields, models


class CpanelMailboxTemplate(models.Model):
    _name = "cpanel.mailbox.template"
    _description = "cPanel Mailbox Template"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    quota_mb = fields.Integer(string="Default Quota (MB)", default=1024, required=True)
    tag_ids = fields.Many2many("cpanel.mailbox.tag", string="Default Tags")
    active = fields.Boolean(default=True)

