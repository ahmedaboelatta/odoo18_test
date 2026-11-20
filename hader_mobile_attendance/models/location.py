from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HaderWorkLocation(models.Model):
    _name = "hader.work.location"
    _description = "Hader Work Location"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, name"

    name = fields.Char(required=True, translate=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True, tracking=True
    )
    active = fields.Boolean(default=True, tracking=True)
    latitude = fields.Float(required=True, digits=(10, 7), tracking=True)
    longitude = fields.Float(required=True, digits=(10, 7), tracking=True)
    radius_m = fields.Float(required=True, default=150.0, tracking=True)
    maximum_accuracy_m = fields.Float(required=True, default=300.0, tracking=True)

    @api.constrains("latitude", "longitude", "radius_m", "maximum_accuracy_m")
    def _check_coordinates(self):
        for record in self:
            if not -90 <= record.latitude <= 90 or not -180 <= record.longitude <= 180:
                raise ValidationError(_("Work location coordinates are invalid."))
            if record.radius_m <= 0 or record.maximum_accuracy_m <= 0:
                raise ValidationError(_("Radius and maximum accuracy must be positive."))
