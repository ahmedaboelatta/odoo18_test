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


class BaseModel(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def _get_recycle_bin_model(self):
        try:
            return self.env.ref('recycle_bin.model_recycle_bin')
        except ValueError:
            return False

    def unlink(self):
        if self.env.context.get('bypass_recycle_bin'):
            return super(BaseModel, self).unlink()

        recycle_model = self._get_recycle_bin_model()
        if not recycle_model:
            return super(BaseModel, self).unlink()

        if self._name in (recycle_model._name, *TRANSIENT_MODELS):
            return super(BaseModel, self).unlink()

        if getattr(self, '_transient', False):
            return super(BaseModel, self).unlink()

        ir_attachment = self.env['ir.attachment']
        vals_to_create = []

        for record in self.sorted(key=lambda r: r.id):
            try:
                if hasattr(record, 'name') and record.name:
                    record_name = record.name
                elif hasattr(record, 'display_name'):
                    record_name = record.display_name
                else:
                    record_name = ''
            except Exception:
                record_name = ''

            values = {
                'record_name': record_name,
                'model': record._name,
                'id': record.id,
            }

            fields_to_store = ['name', 'display_name']
            for field_name in fields_to_store:
                if field_name in self.env[record._name]._fields and field_name not in values:
                    try:
                        values[field_name] = record[field_name]
                    except Exception:
                        pass

            vals_to_create.append({
                'res_model': record._name,
                'res_id': record.id,
                'record_name': record_name,
                'deleted_by_id': self.env.uid,
                'original_data': json.dumps(values, default=self._json_default, separators=(',', ':')),
            })

        recycle_records = self.env['recycle.bin'].create(vals_to_create)

        for recycle_record, original_record in zip(recycle_records, self):
            attachment_ids = ir_attachment.sudo().search([
                ('res_model', '=', original_record._name),
                ('res_id', '=', original_record.id),
            ])
            if attachment_ids:
                recycle_record.attachment_ids = [(4, aid) for aid in attachment_ids.ids]

        return super(BaseModel, self.with_context(bypass_recycle_bin=True)).unlink()

    @staticmethod
    def _json_default(obj):
        return str(obj)
