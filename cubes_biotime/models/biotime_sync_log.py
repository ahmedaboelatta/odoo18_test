from odoo import models, fields

class BioTimeSyncLog(models.Model):
    _name = 'biotime.sync.log'
    _description = 'BioTime Sync Log'
    _order = 'create_date desc'

    terminal_id = fields.Many2one('biotime.terminal', string='Terminal')
    sync_date = fields.Date('Sync Date')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('failed', 'Failed')
    ], default='pending')
    error_message = fields.Text('Error Message')
    records_processed = fields.Integer('Records Processed')
    duration = fields.Float('Duration (seconds)') 