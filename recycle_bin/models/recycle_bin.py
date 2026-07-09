from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json

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

    def action_restore(self):
        """ استعادة السجل المحذوف بالكامل وإعادة ربط مرفقاته """
        self.ensure_one()
        if not self.original_data:
            raise UserError(_("No data available to restore this record."))

        try:
            # 1. تحويل نص الـ JSON إلى قاموس بيانات مقروء لأودو
            data = json.loads(self.original_data)

            # 2. تنظيف البيانات من الحقول التلقائية التي قد تسبب مشاكل أثناء الإنشاء الجديد
            fields_to_remove = ['id', 'create_uid', 'create_date', 'write_uid', 'write_date', '__last_update']
            for field in fields_to_remove:
                if field in data:
                    data.pop(field)

            # 3. إنشاء السجل من جديد في الموديل الأصلي الخاص به
            new_record = self.env[self.res_model].with_context(bypass_recycle_bin=True).create(data)

            # 4. إذا كان للسجل مرفقات في السلة، قم بإعادة ربطها بالسجل الجديد المستعاد
            if self.attachment_ids:
                self.attachment_ids.with_context(bypass_recycle_bin=True).write({
                    'res_model': self.res_model,
                    'res_id': new_record.id
                })

            # 5. حذف السجل من السلة بعد نجاح استعادته تماماً
            self.unlink()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Record restored successfully.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise UserError(_("Failed to restore record: %s") % str(e))

    def action_force_delete(self):
        """ الحذف النهائي الفعلي للسجل ومرفقاته من السيستم بالكامل """
        self.ensure_one()
        # حذف كافة المرفقات المرتبطة به نهائياً من قاعدة البيانات والفولدر الفيزيائي
        if self.attachment_ids:
            self.attachment_ids.with_context(bypass_recycle_bin=True).unlink()
        
        # حذف سجل السلة نفسه
        return super(RecycleBin, self).unlink()