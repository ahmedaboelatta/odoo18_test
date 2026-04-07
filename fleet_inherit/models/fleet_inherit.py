from odoo import api, fields, models, _, Command

class FleetLineInherit(models.Model):
    _inherit = 'fleet.vehicle.odometer'

    driver_id_new = fields.Many2one("res.partner", string="Driver", readonly=False)

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        if self.vehicle_id:
            self.driver_id_new = self.vehicle_id.driver_id  # Assuming `driver_id` exists on `fleet.vehicle`
        else:
            self.driver_id_new = False