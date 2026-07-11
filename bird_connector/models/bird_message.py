from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BirdMessage(models.Model):
    _name = 'bird.message'
    _description = 'Bird Message'
    _order = 'create_date desc'

    organization_id = fields.Many2one('bird.organization', string='Organization', required=True, ondelete='cascade')
    channel_id = fields.Many2one('bird.channel', string='Channel', ondelete='set null')
    contact_id = fields.Many2one('bird.contact', string='Contact', ondelete='set null')
    conversation_id = fields.Many2one('bird.conversation', string='Conversation', ondelete='set null')
    message_id = fields.Char(string='Message ID')
    direction = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ], string='Direction', default='outbound')
    status = fields.Selection([
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
    ], string='Status', default='pending')
    payload = fields.Text(string='Payload')
    response = fields.Text(string='Response')
    error_message = fields.Text(string='Error Message')
    body = fields.Text(string='Body')
    media_url = fields.Char(string='Media URL')
    sent_at = fields.Datetime(string='Sent At')
    delivered_at = fields.Datetime(string='Delivered At')
    read_at = fields.Datetime(string='Read At')
    template_id = fields.Many2one('bird.template', string='Template', ondelete='set null')
    variables_data = fields.Text(string='Variables Data')

    @api.model
    def _cron_cleanup_old_messages(self, days=90):
        from datetime import datetime, timedelta
        cutoff = fields.Datetime.to_string(datetime.now() - timedelta(days=days))
        old_messages = self.search([('create_date', '<', cutoff)])
        old_messages.unlink()
        return True
