# 1. تأكد من عمل import لكلاس BaseModel المباشر من أودو
from odoo import models, api
import json

# 2. تغيير الوراثة لتكون للكلاس البرمجي مباشرة وليس للنص
# قم بمسير سطر _inherit = 'base.model' واجعل الكلاس يرث من models.BaseModel
class BaseModel(models.BaseModel):
    _register = False  # هذه تمنع أودو من إنشاء جدول لهذا الكلاس، وتجبره على تطبيق الكود على كل الموديلات

    def unlink(self):
        # باقي الكود السليم الخاص بك كم هو بدون أي تغيير...
        blacklist_models = [
            'recycle.bin', 'ir.logging', 'ir.cron', 'bus.bus', 
            'res.users.log', 'mail.channel', 'mail.ice.server',
            'ir.attachment', 'mail.message', 'mail.followers',
            'mail.activity', 'mail.notification', 'account.move.line'
        ]
        
        if self._name in blacklist_models:
            return super(BaseModel, self).unlink()

        if hasattr(self.env.cr, 'in_recycle_bin_processing') and self.env.cr.in_recycle_bin_processing:
            return super(BaseModel, self).unlink()

        # Set the lock
        self.env.cr.in_recycle_bin_processing = True

        RecycleBin = self.env['recycle.bin']
        Attachment = self.env['ir.attachment']
        Message = self.env['mail.message']

        try:
            for record in self:
                try:
                    # Capture parent record fields safely
                    record_values = record.read()[0] if record.read() else {}
                    
                    # Capture chatter messages before they are purged by Odoo cascade
                    messages = Message.search([('model', '=', record._name), ('res_id', '=', record.id)])
                    chatter_log = []
                    for msg in messages:
                        chatter_log.append(f"[{msg.date}] {msg.author_id.name or 'System'}: {msg.body}")
                    
                    # Create ONLY ONE master container record in the Recycle Bin
                    bin_record = RecycleBin.create({
                        'res_model': record._name,
                        'res_id': record.id,
                        'record_name': record.display_name or record.name or f"Deleted {record._name} ({record.id})",
                        'original_data': json.dumps(record_values, default=str),
                        'chatter_backup': "\n".join(chatter_log),
                        'deleted_by_id': self.env.user.id,
                    })

                    # Move and re-route attachments safely
                    attachments = Attachment.search([('res_model', '=', record._name), ('res_id', '=', record.id)])
                    if attachments:
                        attachments.write({
                            'res_model': 'recycle.bin',
                            'res_id': bin_record.id
                        })
                        bin_record.write({'attachment_ids': [(6, 0, attachments.ids)]})

                except Exception:
                    continue

            # 3. Standard execution of Odoo delete sequence
            return super(BaseModel, self).unlink()

        finally:
            # ALWAYS release the lock
            self.env.cr.in_recycle_bin_processing = False