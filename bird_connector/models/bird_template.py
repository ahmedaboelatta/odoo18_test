from odoo import api, fields, models, _
from odoo.exceptions import UserError
import json


class BirdTemplateVariable(models.Model):
    _name = 'bird.template.variable'
    _description = 'Bird Template Variable'
    _order = 'sequence, id'

    template_id = fields.Many2one('bird.template', string='Template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    bird_variable = fields.Char(string='Bird Placeholder', required=True, help='e.g., {{1}}, {{2}}')
    odoo_model = fields.Char(string='Odoo Model')
    odoo_field = fields.Char(string='Odoo Field')
    expression = fields.Char(string='Jinja2/QWeb Expression', help='e.g., object.partner_id.name')
    example_value = fields.Char(string='Example Value')
    is_active = fields.Boolean(string='Active', default=True)


class BirdTemplate(models.Model):
    _name = 'bird.template'
    _description = 'Bird Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    organization_id = fields.Many2one('bird.organization', string='Organization', required=True, ondelete='cascade')
    workspace_id = fields.Many2one('bird.workspace', string='Workspace', ondelete='cascade')
    template_type = fields.Char(string='Template Type', default='channelTemplate')
    bird_template_id = fields.Char(string='Bird Template ID')
    project_id = fields.Char(string='Project ID')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('pending', 'Pending'),
    ], string='Status', default='draft')
    supported_platforms = fields.Char(string='Supported Platforms', help='JSON array, e.g., ["whatsapp"]')
    locales = fields.Char(string='Locales', help='JSON array, e.g., ["ar"]')
    default_locale = fields.Char(string='Default Locale', default='ar')
    short_links_enabled = fields.Boolean(string='Short Links Enabled', default=False)
    short_links_domain = fields.Char(string='Short Links Domain')
    is_cloneable = fields.Boolean(string='Is Cloneable', default=False)
    variable_ids = fields.One2many('bird.template.variable', 'template_id', string='Variables')
    platform_info = fields.Text(string='Platform Info')
    platform_content = fields.Html(string='Platform Content')
    header_image_url = fields.Char(string='Header Image URL')
    header_video_url = fields.Char(string='Header Video URL')
    header_text = fields.Text(string='Header Text')
    body_text = fields.Text(string='Body Text')
    footer_text = fields.Text(string='Footer Text')
    button_url = fields.Char(string='Button URL')
    button_text = fields.Char(string='Button Text', default='اطلب الآن')
    channel_ids = fields.Many2many('bird.channel', string='Channels')
    message_ids = fields.One2many('bird.message', 'template_id', string='Messages')
    message_count = fields.Integer(string='Message Count', compute='_compute_message_count')

    @api.depends('message_ids')
    def _compute_message_count(self):
        Message = self.env['bird.message']
        for rec in self:
            rec.message_count = Message.search_count([
                ('template_id', '=', rec.id),
            ])

    @api.onchange('supported_platforms')
    def _onchange_supported_platforms(self):
        if self.supported_platforms:
            try:
                data = json.loads(self.supported_platforms)
                if not isinstance(data, list):
                    self.supported_platforms = json.dumps(['whatsapp'])
            except Exception:
                self.supported_platforms = json.dumps(['whatsapp'])

    @api.onchange('locales')
    def _onchange_locales(self):
        if self.locales:
            try:
                data = json.loads(self.locales)
                if not isinstance(data, list):
                    self.locales = json.dumps(['en'])
            except Exception:
                self.locales = json.dumps(['en'])

    def action_sync_to_bird(self):
        self.ensure_one()
        if not self.organization_id or not self.organization_id.api_key:
            raise UserError(_('Organization and API Key are required for sync'))
        organization = self.organization_id
        payload = {
            'name': self.name,
            'type': self.template_type,
            'organizationId': organization.bird_id,
            'workspaceId': self.workspace_id.workspace_id if self.workspace_id else None,
            'language': self.default_locale,
            'supportedPlatforms': json.loads(self.supported_platforms or '["whatsapp"]'),
            'shortLinksEnabled': self.short_links_enabled,
        }
        if self.bird_template_id:
            endpoint = f'/workspaces/{self.workspace_id.workspace_id}/templates/{self.bird_template_id}'
            result = organization._make_api_request('PUT', endpoint, data=payload)
        else:
            endpoint = f'/workspaces/{self.workspace_id.workspace_id}/templates'
            result = organization._make_api_request('POST', endpoint, data=payload)
            if result and 'id' in result:
                self.bird_template_id = result['id']
                self.project_id = result.get('projectId', '')
        self.status = 'active'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Template Synced'),
                'message': _('Template synced to Bird successfully'),
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def _cron_sync_template_statuses(self):
        orgs = self.env['bird.organization'].search([('state', '=', 'active'), ('api_key', '!=', False)])
        templates = self.search([('bird_template_id', '!=', False), ('workspace_id', '!=', False)])
        for template in templates:
            try:
                if not template.workspace_id or not template.workspace_id.workspace_id:
                    continue
                endpoint = f"/workspaces/{template.workspace_id.workspace_id}/templates/{template.bird_template_id}"
                result = template.organization_id._make_api_request('GET', endpoint)
                if result:
                    status_raw = result.get('status', '').lower()
                    status_map = {'draft': 'draft', 'active': 'active', 'pending': 'pending', 'rejected': 'draft'}
                    template.status = status_map.get(status_raw, template.status)
            except Exception as e:
                _logger.warning('Failed to sync template %s: %s', template.name, e)
        return True
