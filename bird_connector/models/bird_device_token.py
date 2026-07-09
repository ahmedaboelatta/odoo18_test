from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BirdDeviceToken(models.Model):
    _name = 'bird.device.token'
    _description = 'Bird Device Token'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True)
    organization_id = fields.Many2one('bird.organization', string='Organization', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Partner', ondelete='cascade')
    token = fields.Text(string='Device Token', required=True)
    platform = fields.Selection([
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('web', 'Web'),
    ], string='Platform')
    device_id = fields.Char(string='Device ID')
    active = fields.Boolean(string='Active', default=True)
    last_used = fields.Datetime(string='Last Used')
