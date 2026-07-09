from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BirdContact(models.Model):
    _name = 'bird.contact'
    _description = 'Bird Contact'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _inherits = {'res.partner': 'partner_id'}

    partner_id = fields.Many2one('res.partner', string='Partner', required=True, ondelete='cascade')
    organization_id = fields.Many2one('bird.organization', string='Organization', required=True, ondelete='cascade')
    contact_id = fields.Char(string='Bird Contact ID')
    phone_number = fields.Char(string='Phone Number')
    email = fields.Char(string='Email')
    channel = fields.Selection([
        ('sms', 'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('voice', 'Voice'),
        ('email', 'Email'),
    ], string='Channel', default='whatsapp')
    tags = fields.Char(string='Tags')
    custom_data = fields.Text(string='Custom Data')
    message_ids = fields.One2many('bird.message', 'contact_id', string='Messages')
    conversation_ids = fields.One2many('bird.conversation', 'contact_id', string='Conversations')

    @api.depends('partner_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = rec.partner_id.display_name if rec.partner_id else ''
