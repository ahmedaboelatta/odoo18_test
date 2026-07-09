from odoo import models, api
import json

# 1. نحتفظ بالميثود الأصلية للحذف الخاصة بأودو في الذاكرة قبل التعديل عليها
original_unlink = models.BaseModel.unlink

def custom_unlink(self):
    # قائمة الموديلات الفرعية والتقنية المطلوب حظرها تماماً من إنشاء سطور
    blacklist_models = [
        'recycle.bin', 'ir.logging', 'ir.cron', 'bus.bus', 
        'res.users.log', 'mail.channel', 'mail.ice.server',
        'ir.attachment', 'mail.message', 'mail.followers',
        'mail.activity', 'mail.notification', 'account.move.line',
        'account.full.reconcile', 'account.partial.reconcile' # أضفنا موديلات التسوية الظاهرة بالصورة
    ]
    
    # أ) إذا كان الموديل الحالي في القائمة السوداء، احذف فوراً بدون حفظ
    if self._name in blacklist_models:
        return original_unlink(self)

    # ب) إذا كان هناك قفل مفعل للحذف التابع، احذف فوراً
    if hasattr(self.env.cr, 'in_recycle_bin_processing') and self.env.cr.in_recycle_bin_processing:
        return original_unlink(self)

    # تفعيل القفل لمنع الجداول الفرعية من الدخول هنا
    self.env.cr.in_recycle_bin_processing = True

    RecycleBin = self.env['recycle.bin']
    Attachment = self.env['ir.attachment']
    Message = self.env['mail.message']

    try:
        for record in self:
            try:
                # قراءة قيم الحقول الأساسية
                record_values = record.read()[0] if record.read() else {}
                
                # جلب الـ Chatter والرسائل قبل حذفها كاسكيد
                messages = Message.search([('model', '=', record._name), ('res_id', '=', record.id)])
                chatter_log = []
                for msg in messages:
                    chatter_log.append(f"[{msg.date}] {msg.author_id.name or 'System'}: {msg.body}")
                
                # إنشاء سجل حاوي واحد فقط في السلة
                bin_record = RecycleBin.create({
                    'res_model': record._name,
                    'res_id': record.id,
                    'record_name': record.display_name or record.name or f"Deleted {record._name} ({record.id})",
                    'original_data': json.dumps(record_values, default=str),
                    'chatter_backup': "\n".join(chatter_log),
                    'deleted_by_id': self.env.user.id,
                })

                # نقل المرفقات بأمان إلى سجل السلة
                attachments = Attachment.search([('res_model', '=', record._name), ('res_id', '=', record.id)])
                if attachments:
                    attachments.write({
                        'res_model': 'recycle.bin',
                        'res_id': bin_record.id
                    })
                    bin_record.write({'attachment_ids': [(6, 0, attachments.ids)]})

            except Exception:
                continue

        # استدعاء الحذف الفعلي للريكورد الأساسي من قاعدة البيانات
        return original_unlink(self)

    finally:
        # فك القفل دائماً لضمان استقرار السيرفر
        self.env.cr.in_recycle_bin_processing = False

# 2. السطر السحري: نقوم بحقن الدالة الجديدة داخل كلاس أودو الأساسي مباشرة في الذاكرة
models.BaseModel.unlink = custom_unlink