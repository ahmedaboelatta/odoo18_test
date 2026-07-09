from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BirdConversation(models.Model):
    _name = 'bird.conversation'
    _description = 'Bird Conversation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'last_message_at desc'

    organization_id = fields.Many2one('bird.organization', string='Organization', required=True, ondelete='cascade')
    workspace_id = fields.Many2one('bird.workspace', string='Workspace', ondelete='set null')
    channel_id = fields.Many2one('bird.channel', string='Channel', ondelete='set null')
    contact_id = fields.Many2one('bird.contact', string='Contact', ondelete='set null')
    conversation_id = fields.Char(string='Conversation ID')
    contact_name = fields.Char(string='Contact Name')
    contact_phone = fields.Char(string='Contact Phone')
    status = fields.Selection([
        ('active', 'Active'),
        ('closed', 'Closed'),
    ], string='Status', default='active')
    last_message_at = fields.Datetime(string='Last Message At')
    message_ids = fields.One2many('bird.message', 'conversation_id', string='Messages')
    message_count = fields.Integer(string='Message Count', compute='_compute_message_count')

    @api.depends('message_ids')
    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)
