from odoo import api, fields, models, _
from odoo.exceptions import UserError
import json


class BirdSyncMixin(models.AbstractModel):
    _name = 'bird.sync.mixin'
    _description = 'Bird Sync Mixin'

    bird_template_id = fields.Many2one('bird.template', string='Bird Template')
    bird_variables = fields.Text(string='Bird Variables', default='{}')
    bird_sync_state = fields.Selection([
        ('none', 'None'),
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ], string='Bird Sync State', default='none')
    bird_message_id = fields.Char(string='Bird Message ID')
    bird_last_sync = fields.Datetime(string='Last Bird Sync')

    def _prepare_bird_variables(self):
        self.ensure_one()
        try:
            variables_data = json.loads(self.bird_variables or '{}')
        except Exception:
            variables_data = {}

        if self.bird_template_id:
            for var in self.bird_template_id.variable_ids.filtered(lambda v: v.is_active):
                if var.expression and not variables_data.get(var.bird_variable):
                    try:
                        val = eval(var.expression, {'object': self})
                        variables_data[var.bird_variable] = str(val) if val else ''
                    except Exception as e:
                        _logger = self.env['ir.logging'].sudo().search([('name', '=', 'Bird Sync Mixin')], limit=1)
                        _logger.create({
                            'name': 'Bird Sync Mixin',
                            'type': 'server',
                            'level': 'warning',
                            'message': f"Failed to evaluate expression {var.expression} on {self._name} {self.id}: {e}",
                            'path': 'bird_connector/models/bird_template.py',
                            'line': 0,
                            'func': '_prepare_bird_variables',
                        })
        return variables_data

    def action_send_bird_message(self):
        self.ensure_one()
        if not self.bird_template_id:
            raise UserError(_('No Bird template configured'))
        organization = self.bird_template_id.organization_id
        if not organization or not organization.api_key:
            raise UserError(_('Organization API key is missing'))

        variables = self._prepare_bird_variables()
        payload = {
            'from': self.bird_template_id.workspace_id.channel_ids[:1].phone_number if self.bird_template_id.workspace_id.channel_ids else '',
            'to': self.bird_variables.get('recipient') or getattr(self, 'partner_id', False).phone if hasattr(self, 'partner_id') and self.partner_id else '',
            'content': {
                'text': self.bird_template_id.body_text,
                'variables': [variables.get(f'{{{{{i+1}}}}}', '') for i in range(len(self.bird_template_id.variable_ids))],
            },
            'channelId': self.bird_template_id.workspace_id.channel_ids[:1].channel_id if self.bird_template_id.workspace_id.channel_ids else '',
            'type': 'text',
        }

        try:
            result = organization._make_api_request('POST', '/messages', data=payload)
            message_id = result.get('id') if result else ''
            self.bird_message_id = message_id
            self.bird_sync_state = 'sent'
            self.bird_last_sync = fields.Datetime.now()

            self.env['bird.message'].sudo().create({
                'organization_id': organization.id,
                'message_id': message_id,
                'direction': 'outbound',
                'status': 'sent',
                'payload': json.dumps(payload, ensure_ascii=False),
                'response': json.dumps(result, ensure_ascii=False) if result else '',
                'template_id': self.bird_template_id.id,
                'body': self.bird_template_id.body_text,
                'variables_data': json.dumps(variables, ensure_ascii=False),
            })
            return True
        except UserError as e:
            self.bird_sync_state = 'failed'
            raise

    @api.model
    def _cron_send_pending_bird_messages(self):
        records = self.search([('bird_sync_state', '=', 'pending'), ('bird_template_id', '!=', False)])
        for rec in records:
            try:
                rec.action_send_bird_message()
            except Exception as e:
                self.env.cr.rollback()
                continue
        return True
