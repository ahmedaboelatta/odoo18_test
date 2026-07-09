from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BirdChannel(models.Model):
    _name = 'bird.channel'
    _description = 'Bird Channel'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, track_visibility='onchange')
    organization_id = fields.Many2one('bird.organization', string='Organization', required=True, ondelete='cascade')
    workspace_id = fields.Many2one('bird.workspace', string='Workspace', ondelete='cascade')
    channel_type = fields.Selection([
        ('whatsapp', 'WhatsApp'),
        ('sms', 'SMS'),
        ('voice', 'Voice'),
        ('email', 'Email'),
        ('messenger', 'Messenger'),
        ('instagram', 'Instagram'),
        ('telegram', 'Telegram'),
    ], string='Channel Type', default='whatsapp', required=True)
    channel_id = fields.Char(string='Bird Channel ID')
    phone_number = fields.Char(string='Phone Number')
    status = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ], string='Status', default='active')
    message_ids = fields.One2many('bird.message', 'channel_id', string='Messages')
    conversation_ids = fields.One2many('bird.conversation', 'channel_id', string='Conversations')
