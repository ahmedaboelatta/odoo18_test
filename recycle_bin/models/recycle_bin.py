from odoo import models, fields

class RecycleBin(models.Model):
    _name = 'recycle.bin'
    _description = 'Recycle Bin'
    _order = 'deletion_date desc'

    record_name = fields.Char(string='Record Name', required=True)
    res_model = fields.Char(string='Model', required=True)
    res_id = fields.Integer(string='Resource ID', required=True)
    deleted_by_id = fields.Many2one('res.users', string='Deleted By', default=lambda self: self.env.user)
    deletion_date = fields.Datetime(string='Deletion Date', default=fields.Datetime.now)
    original_data = fields.Text(string='Original Data (JSON)')
    chatter_backup = fields.Text(string='Chatter History Backup')
    attachment_ids = fields.Many2many('ir.attachment', string='Preserved Attachments')