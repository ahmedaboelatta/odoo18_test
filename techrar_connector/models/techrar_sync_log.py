from odoo import fields, models


class TechrarSyncLog(models.Model):
    _name = 'techrar.sync.log'
    _description = 'Techrar Sync Log'
    _order = 'create_date desc, id desc'

    techrar_order_id = fields.Char(index=True)
    sale_order_id = fields.Many2one('sale.order', ondelete='set null')
    status = fields.Selection([
        ('imported', 'Imported'),
        ('processed', 'Processed'),
        ('invoiced', 'Invoiced'),
        ('needs_mapping', 'Needs Mapping'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ], required=True, index=True)
    message = fields.Text()
    run_source = fields.Selection([('manual', 'Manual'), ('cron', 'Scheduled')], required=True)
