from odoo import api, fields, models, _
from odoo.exceptions import UserError
import json


class RecycleBin(models.Model):
    _name = 'recycle.bin'
    _description = 'Recycle Bin'
    _order = 'deletion_date desc'

    res_model = fields.Char(string='Model', required=True)
    res_id = fields.Integer(string='Record ID', required=True)
    record_name = fields.Char(string='Record Name')
    deleted_by_id = fields.Many2one('res.users', string='Deleted By')
    deletion_date = fields.Datetime(string='Deletion Date', default=fields.Datetime.now)
    original_data = fields.Text(string='Original Data')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')

    def action_restore(self):
        self.ensure_one()
        try:
            data = json.loads(self.original_data or '{}')
        except Exception:
            data = {}

        model_obj = self.env[self.res_model]
        fields_info = model_obj.fields_get()
        invalid_fields = [f for f in data if f not in fields_info]
        for field_name in invalid_fields:
            del data[field_name]

        new_record = model_obj.create(data)

        if self.attachment_ids:
            self.attachment_ids.write({
                'res_model': self.res_model,
                'res_id': new_record.id,
            })

        self.unlink()
        return {
            'type': 'ir.actions.act_window_close',
        }

    def action_force_delete(self):
        self.ensure_one()
        if not self.env.user.has_group('recycle_bin.group_recycle_bin_manager'):
            raise UserError(_('Only Recycle Bin Managers can force delete.'))

        import os

        attachments = self.attachment_ids
        for attachment in attachments.filtered(lambda a: a.store_fname and a.storage == 'file'):
            full_path = attachment._full_path(attachment.store_fname)
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
            except OSError:
                pass

        attachments.sudo().unlink()
        self.unlink()
        return True
