from odoo import models, api
import json

class BaseModel(models.AbstractModel):
    _inherit = 'base.model'

    @api.model
    def _get_recycle_bin_excluded_models(self):
        return [
            'recycle.bin', 'ir.logging', 'ir.cron', 'bus.bus', 
            'res.users.log', 'mail.channel', 'mail.ice.server',
            'ir.attachment', 'mail.message', 'mail.followers',
            'mail.activity', 'mail.notification'
        ]

    def unlink(self):
        # 1. Global Bypass Check: If the system or another process locked it, do not process.
        if hasattr(self.env.cr, 'in_recycle_bin_processing') and self.env.cr.in_recycle_bin_processing:
            return super(BaseModel, self).unlink()

        # 2. Skip technical excluded models immediately
        if self._name in self._get_recycle_bin_excluded_models():
            return super(BaseModel, self).unlink()

        # Activate global lock on the cursor to block ALL cascaded sub-deletions
        self.env.cr.in_recycle_bin_processing = True

        RecycleBin = self.env['recycle.bin']
        Attachment = self.env['ir.attachment']
        Message = self.env['mail.message']

        try:
            for record in self:
                try:
                    # Capture the parent record fields safely
                    record_values = record.read()[0] if record.read() else {}
                    
                    # Capture chatter messages before they are cascaded/purged
                    messages = Message.search([('model', '=', record._name), ('res_id', '=', record.id)])
                    chatter_log = []
                    for msg in messages:
                        chatter_log.append(f"[{msg.date}] {msg.author_id.name or 'System'}: {msg.body}")
                    
                    # Create ONE single parent record container in the Recycle Bin
                    bin_record = RecycleBin.create({
                        'res_model': record._name,
                        'res_id': record.id,
                        'record_name': record.display_name or record.name or f"Deleted {record._name} ({record.id})",
                        'original_data': json.dumps(record_values, default=str),
                        'chatter_backup': "\n".join(chatter_log),
                        'deleted_by_id': self.env.user.id,
                    })

                    # Safely link and move attachments to the Recycle Bin container
                    attachments = Attachment.search([('res_model', '=', record._name), ('res_id', '=', record.id)])
                    if attachments:
                        attachments.write({
                            'res_model': 'recycle.bin',
                            'res_id': bin_record.id
                        })
                        bin_record.write({'attachment_ids': [(6, 0, attachments.ids)]})

                except Exception:
                    continue # Skip current record if read/write fails, prevent blocking the system

            # 3. CRITICAL FIX: Execute super().unlink() OUTSIDE the loop once for all records.
            # This ensures Odoo handles cascading while our global lock is fully active.
            return super(BaseModel, self).unlink()

        finally:
            # ALWAYS release the lock to prevent database freezing
            self.env.cr.in_recycle_bin_processing = False