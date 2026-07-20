from odoo import models, fields, api


class BirdMessageLog(models.Model):
    _name = "bird.message.log"
    _description = "Bird Message Log"
    _order = "create_date desc"

    channel_id = fields.Many2one("bird.channel", string="Channel", required=True)
    workspace_id = fields.Many2one(
        "bird.workspace", string="Workspace", related="channel_id.workspace_id", store=True
    )
    organization_id = fields.Many2one(
        "bird.organization",
        string="Organization",
        related="channel_id.organization_id",
        store=True,
    )
    receiver_mobile = fields.Char(string="Receiver Mobile/Email", required=True)
    template_id = fields.Many2one("bird.template", string="Template")
    project_id = fields.Char(string="Project ID")
    version_id = fields.Char(string="Version ID")
    locale = fields.Char(string="Locale", default="en")
    parameters = fields.Text(string="Parameters")
    status = fields.Selection(
        [
            ("sent", "Sent"),
            ("delivered", "Delivered"),
            ("read", "Read"),
            ("failed", "Failed"),
        ],
        string="Status",
        default="sent",
    )
    error_message = fields.Text(string="Error Message")
    bird_response = fields.Text(string="Bird API Response")
    send_date = fields.Datetime(string="Send Date", default=fields.Datetime.now)
