from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import json


TRANSIENT_MODELS = (
    'ir.model',
    'ir.model.fields',
    'ir.model.access',
    'ir.model.data',
    'ir.model.constraint',
    'ir.model.relation',
    'ir.model.relation.field',
    'ir.module.module',
    'ir.module.module.dependency',
    'ir.module.module.exclusion',
    'ir.module.category',
    'res.groups',
    'res.users',
    'res.lang',
    'res.config.settings',
    'ir.ui.view',
    'ir.ui.menu',
    'ir.actions.act_window',
    'ir.actions.act_url',
    'ir.actions.server',
    'ir.actions.report',
    'ir.actions.client',
    'ir.sequence',
    'ir.cron',
    'ir.logging',
    'ir.http',
    'ir.http.route',
    'bus.bus',
)


from odoo import models, api
import json

class BaseModel(models.AbstractModel):
    _inherit = 'base.model'

    @api.model
    def _get_recycle_bin_excluded_models(self):
        return [
            'recycle.bin', 'ir.logging', 'ir.cron', 'bus.bus', 
            'res.users.log', 'mail.channel', 'mail.ice.server'
        ]

    def unlink(self):
        # Step 1: Skip if this is a cascaded unlink or an excluded technical model
        if self.env.context.get('bypass_recycle_bin') or self._name in self._get_recycle_bin_excluded_models():
            return super(BaseModel, self).unlink()

        RecycleBin = self.env['recycle.bin']
        Attachment = self.env['ir.attachment']
        Message = self.env['mail.message']

        for record in self:
            try:
                # Step 2: Extract record data and its One2Many lines safely before deletion
                record_values = record.read()[0] if record.read() else {}
                
                # Step 3: Capture chatter messages associated with this specific parent record
                messages = Message.search([('model', '=', record._name), ('res_id', '=', record.id)])
                chatter_log = []
                for msg in messages:
                    chatter_log.append(f"[{msg.date}] {msg.author_id.name or 'System'}: {msg.body}")
                
                # Step 4: Create ONE main Recycle Bin entry for the parent record
                bin_record = RecycleBin.create({
                    'res_model': record._name,
                    'res_id': record.id,
                    'record_name': record.display_name or record.name or 'Unnamed Record',
                    'original_data': json.dumps(record_values, default=str),
                    'chatter_backup': "\n".join(chatter_log),
                    'deleted_by_id': self.env.user.id,
                })

                # Step 5: Safely re-route and link original attachments to our Recycle Bin record
                attachments = Attachment.search([('res_model', '=', record._name), ('res_id', '=', record.id)])
                if attachments:
                    attachments.with_context(bypass_recycle_bin=True).write({
                        'res_model': 'recycle.bin',
                        'res_id': bin_record.id
                    })
                    bin_record.write({'attachment_ids': [(6, 0, attachments.ids)]})

            except Exception as e:
                # Fallback to prevent blocking the system if serialization fails on complex fields
                continue

        # Step 6: Trigger the actual purge with context to stop child models from generating new rows
        return super(BaseModel, self.with_context(bypass_recycle_bin=True)).unlink()

    @staticmethod
    def _json_default(obj):
        return str(obj)
