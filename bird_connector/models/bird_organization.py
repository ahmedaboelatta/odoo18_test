from odoo import api, fields, models, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)


class BirdOrganization(models.Model):
    _name = 'bird.organization'
    _description = 'Bird Organization'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, track_visibility='onchange')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
    ], string='Status', default='draft', track_visibility='onchange')
    api_key = fields.Char(string='API Key', password=True, required=True)
    bird_id = fields.Char(string='Bird Organization ID')
    wallet_balance = fields.Float(string='Wallet Balance', readonly=True)
    currency_code = fields.Char(string='Currency Code', readonly=True)
    low_balance_threshold = fields.Float(string='Low Balance Threshold', default=10.0)
    workspace_ids = fields.One2many('bird.workspace', 'organization_id', string='Workspaces')
    channel_ids = fields.One2many('bird.channel', 'organization_id', string='Channels')
    message_ids = fields.One2many('bird.message', 'organization_id', string='Messages')
    conversation_ids = fields.One2many('bird.conversation', 'organization_id', string='Conversations')
    template_ids = fields.One2many('bird.template', 'organization_id', string='Templates')

    @api.model
    def _get_bird_api_base_url(self):
        return 'https://rest.messagebird.com/v1'

    def _get_bird_headers(self):
        self.ensure_one()
        return {
            'Authorization': f'AccessKey {self.api_key}',
            'Content-Type': 'application/json',
        }

    def _make_api_request(self, method, endpoint, data=None, params=None):
        self.ensure_one()
        import requests
        base_url = self._get_bird_api_base_url()
        url = f"{base_url}{endpoint}"
        headers = self._get_bird_headers()
        timeout = 30
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=headers, json=data, timeout=timeout)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=timeout)
            else:
                raise UserError(_('Unsupported HTTP method'))
            response.raise_for_status()
            if response.content:
                return response.json()
            return None
        except requests.exceptions.Timeout:
            raise UserError(_('Bird API request timed out'))
        except requests.exceptions.ConnectionError:
            raise UserError(_('Cannot connect to Bird API'))
        except requests.exceptions.HTTPError as e:
            raise UserError(_('Bird API Error: %s') % str(e))
        except Exception as e:
            raise UserError(_('Bird API request failed: %s') % str(e))

    def action_check_connection(self):
        self.ensure_one()
        try:
            result = self._make_api_request('GET', '/balance')
            self.wallet_balance = result.get('amount', 0.0)
            self.currency_code = result.get('currency', '')
            self.state = 'active'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Balance: %s %s') % (self.wallet_balance, self.currency_code),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    @api.model
    def _cron_sync_balances(self):
        orgs = self.search([('state', '=', 'active'), ('api_key', '!=', False)])
        for org in orgs:
            try:
                result = org._make_api_request('GET', '/balance')
                org.wallet_balance = result.get('amount', 0.0)
                org.currency_code = result.get('currency', '')
                if org.wallet_balance < org.low_balance_threshold:
                    org.message_post(body=_('Low balance warning: %s %s') % (org.wallet_balance, org.currency_code), message_type='comment', subtype_id=False)
            except Exception as e:
                _logger.warning('Failed to sync balance for organization %s: %s', org.name, e)
        return True
