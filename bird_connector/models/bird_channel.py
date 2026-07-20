from odoo import models, fields, api


class BirdChannel(models.Model):
    _name = "bird.channel"
    _description = "Bird Channel"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Channel Name", required=True, tracking=True)
    channel_id = fields.Char(string="Channel ID", required=True, tracking=True)
    channel_type = fields.Selection(
        [
            ("whatsapp", "WhatsApp"),
            ("email", "Email"),
            ("sms", "SMS"),
            ("telegram", "Telegram"),
            ("other", "Other"),
        ],
        string="Channel Type",
        default="whatsapp",
        required=True,
        tracking=True,
    )
    workspace_id = fields.Many2one(
        "bird.workspace", string="Workspace", required=True, ondelete="cascade"
    )
    organization_id = fields.Many2one(
        "bird.organization",
        string="Organization",
        related="workspace_id.organization_id",
        store=True,
    )
    state = fields.Selection(
        [("connected", "Connected"), ("disconnected", "Disconnected")],
        string="Connection State",
        default="connected",
        tracking=True,
    )
    connected_account = fields.Char(string="Connected Account", tracking=True)
    last_activity = fields.Datetime(string="Last Activity", tracking=True)
