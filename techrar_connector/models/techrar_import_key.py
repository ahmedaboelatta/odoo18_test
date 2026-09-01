from odoo import fields, models


class TechrarImportKey(models.Model):
    _name = 'techrar.import.key'
    _description = 'Techrar Atomic Import Key'
    _order = 'id desc'

    config_id = fields.Many2one('techrar.config', required=True, ondelete='cascade')
    techrar_order_id = fields.Char(required=True, index=True)

    _sql_constraints = [
        (
            'techrar_import_config_order_unique',
            'unique(config_id, techrar_order_id)',
            'This Techrar order already has an import key.',
        ),
    ]
