from odoo import api, models
import json


class BaseModel(models.AbstractModel):
    _inherit = 'base'

    def unlink(self):
        if self.env.context.get('bypass_recycle_bin'):
            return super(BaseModel, self).unlink()

        if self._name in (
            'recycle.bin',
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
        ):
            return super(BaseModel, self).unlink()

        if getattr(self, '_transient', False):
            return super(BaseModel, self).unlink()

        RecycleBin = self.env['recycle.bin']
        Attachment = self.env['ir.attachment']
        vals_to_create = []

        for record in self:
            values = {}
            model_fields = self.env[record._name]._fields
            for field_name, field in model_fields.items():
                if not getattr(field, 'store', False):
                    continue
                try:
                    val = record[field_name]
                    if val is False:
                        val = None
                    elif isinstance(val, models.Model):
                        val = val.ids
                    elif hasattr(val, '__iter__') and not isinstance(val, (str, bytes)):
                        val = list(val)
                    values[field_name] = val
                except Exception:
                    pass

            record_name = record.display_name or record.name or ''

            vals_to_create.append({
                'res_model': record._name,
                'res_id': record.id,
                'record_name': record_name,
                'deleted_by_id': self.env.uid,
                'original_data': json.dumps(values, default=str, separators=(',', ':')),
            })

        recycle_records = RecycleBin.create(vals_to_create)

        for recycle_record, original_record in zip(recycle_records, self):
            attachment_ids = Attachment.sudo().search([
                ('res_model', '=', original_record._name),
                ('res_id', '=', original_record.id),
            ])
            if attachment_ids:
                recycle_record.attachment_ids = [(4, aid) for aid in attachment_ids.ids]

        return super(BaseModel, self.with_context(bypass_recycle_bin=True)).unlink()
