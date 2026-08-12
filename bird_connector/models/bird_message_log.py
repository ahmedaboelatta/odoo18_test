from odoo import fields, models


class BirdMessageLog(models.Model):
    _name = "bird.message.log"
    _description = "Bird Message Log"
    _order = "create_date desc, id desc"

    channel_id = fields.Many2one("bird.channel", string="Channel", required=True, index=True)
    workspace_id = fields.Many2one(
        "bird.workspace", string="Workspace", related="channel_id.workspace_id", store=True, index=True
    )
    organization_id = fields.Many2one(
        "bird.organization", string="Organization", related="channel_id.organization_id", store=True, index=True
    )
    receiver_mobile = fields.Char(string="Receiver Mobile/Email", required=True, index=True)
    message_type = fields.Selection(
        [
            ("template", "Template"),
            ("text", "Text"),
            ("image", "Image"),
            ("file", "File"),
            ("interactive", "Interactive"),
        ],
        string="Message Type",
        default="template",
        required=True,
        index=True,
    )
    template_id = fields.Many2one("bird.template", string="Template", index=True)
    project_id = fields.Char(string="Project ID", index=True)
    version_id = fields.Char(string="Version ID")
    locale = fields.Char(string="Locale", default="en")
    parameters = fields.Text(string="Parameters")
    reference = fields.Char(string="Reference", index=True)

    bird_message_id = fields.Char(string="Bird Message ID", index=True, copy=False)
    bird_status = fields.Char(string="Bird Status", copy=False)
    http_status = fields.Integer(string="HTTP Status", copy=False)

    status = fields.Selection(
        [
            ("queued", "Queued"),
            ("sent", "Sent"),
            ("delivered", "Delivered"),
            ("read", "Read"),
            ("failed", "Failed"),
        ],
        string="Status",
        default="queued",
        required=True,
        index=True,
        copy=False,
    )
    error_message = fields.Text(string="Error Message", copy=False)
    request_payload = fields.Text(string="Request Payload", copy=False)
    bird_response = fields.Text(string="Bird API Response", copy=False)

    send_date = fields.Datetime(string="Sent At", copy=False)
    delivered_at = fields.Datetime(string="Delivered At", copy=False)
    read_at = fields.Datetime(string="Read At", copy=False)
    failed_at = fields.Datetime(string="Failed At", copy=False)
    retry_count = fields.Integer(string="Retry Count", default=0, copy=False)
    last_retry_at = fields.Datetime(string="Last Retry At", copy=False)
