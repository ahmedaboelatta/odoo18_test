import json
import logging
from datetime import datetime, timezone

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class TechrarBranchTag(models.Model):
    _name = 'techrar.branch.tag'
    _description = 'Techrar Branch Tag'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'The branch tag name must be unique.'),
    ]


class TechrarBranch(models.Model):
    _name = 'techrar.branch'
    _description = 'Techrar Branch'
    _order = 'ordering, city_name_en, name'

    name = fields.Char(string='Branch Name (AR)', required=True)
    branch_name_en = fields.Char(string='Branch Name (EN)')
    techrar_branch_id = fields.Char(string='Techrar Branch ID', index=True)
    techrar_location_id = fields.Char(string='Techrar Location ID', index=True)
    city_name_en = fields.Char(string='City Name (EN)')
    city_name_ar = fields.Char(string='City Name (AR)')
    city_id = fields.Char(string='Techrar City ID', index=True)
    country_code = fields.Char()
    city_keywords = fields.Char()
    city_is_supported = fields.Boolean(string='City Supported')
    country_id_techrar = fields.Char(string='Techrar Country ID')
    location_url = fields.Char(string='Map URL')
    latitude = fields.Char()
    longitude = fields.Char()
    address1 = fields.Char(string='Address Line 1')
    address2 = fields.Char(string='Address Line 2')
    formatted_address = fields.Char()
    district = fields.Char(string='District (EN)')
    district_ar = fields.Char(string='District (AR)')
    route = fields.Char()
    street_number = fields.Char()
    postal_code = fields.Char()
    place_id = fields.Char(string='Google Place ID')
    zone_id = fields.Char(string='Techrar Zone ID')
    app_id = fields.Char(string='Techrar App ID')
    restaurant_id = fields.Char(string='Techrar Restaurant ID')
    ordering = fields.Integer()
    branch_hours = fields.Char(string='Branch Hours')
    techrar_is_active = fields.Boolean(string='Active in Techrar', readonly=True)
    is_main = fields.Boolean(string='Main Branch', readonly=True)
    is_dispatch = fields.Boolean(string='Dispatch Branch', readonly=True)
    gender = fields.Char(readonly=True)
    on_demand_opened = fields.Boolean(string='On-demand Enabled', readonly=True)
    on_demand_delivery_price = fields.Float(readonly=True)
    on_demand_min_charge = fields.Float(readonly=True)
    handler_id_techrar = fields.Char(string='Techrar Handler ID', readonly=True)
    handler_user_id_techrar = fields.Char(string='Techrar Handler User ID', readonly=True)
    handler_name = fields.Char(readonly=True)
    handler_username = fields.Char(readonly=True)
    handler_email = fields.Char(readonly=True)
    handler_mobile = fields.Char(readonly=True)
    handler_is_active = fields.Boolean(readonly=True)
    handler_is_manager = fields.Boolean(readonly=True)
    techrar_pickup_handler_only = fields.Boolean(
        string='Techrar Pickup Handler Only', readonly=True,
    )
    is_synced = fields.Boolean(string='Synced in Techrar', readonly=True)
    techrar_is_deleted = fields.Boolean(string='Deleted in Techrar', readonly=True)
    techrar_created_at = fields.Datetime(string='Created in Techrar', readonly=True)
    techrar_modified_at = fields.Datetime(string='Modified in Techrar', readonly=True)
    raw_payload = fields.Text(readonly=True)
    synced_from_locations_api = fields.Boolean(readonly=True, copy=False)
    last_seen_at = fields.Datetime(string='Last Seen in Techrar', readonly=True, copy=False)
    tag_ids = fields.Many2many('techrar.branch.tag', string='Tags')
    employees_only_pickup = fields.Boolean(
        string='Pickup Restricted to Site Employees',
        help=(
            'Enable when only employees of the host company or site may collect '
            'orders from this location. Leave disabled when any customer may enter '
            'the site and collect an order.'
        ),
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        help='Optional mapping to an Odoo warehouse.',
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        help='Optional mapping to an Odoo analytic account.',
    )
    active = fields.Boolean(string='Active', default=True)

    @api.model
    def action_sync_from_techrar(self):
        if not self.env.user.has_group('techrar_connector.module_techrar_connector_manager'):
            raise UserError(_('Only Techrar Connector managers can sync pickup locations.'))
        config = self.env['techrar.config'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not config:
            raise UserError(_('Create a Techrar configuration before syncing pickup locations.'))
        return config.action_sync_pickup_locations()

    @api.model
    def _sync_from_techrar(self, config):
        config.ensure_one()
        restaurant_id = config.pickup_restaurant_id or config.techrar_app_id
        if not restaurant_id or not config.techrar_app_id:
            raise UserError(_('Set the Pickup Restaurant ID and App ID first.'))
        token = self._normalize_bearer_token(config.techrar_api_token)
        if not token:
            raise UserError(_('Set the Techrar API Token first.'))

        url = (
            f"{config.techrar_api_url.rstrip('/')}"
            f"/api/v1/dashboard/admin/restaurants/{restaurant_id}/branches/"
        )
        headers = {
            'Authorization': f'Bearer {token}',
            'app-id': str(config.techrar_app_id),
            'Accept': 'application/json, text/plain, */*',
        }
        created = updated = 0
        seen_ids = set()
        expected_count = None
        page = 1
        while True:
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    params={'page': page},
                    timeout=30,
                )
            except requests.exceptions.Timeout as exc:
                raise UserError(_('Techrar pickup locations request timed out.')) from exc
            except requests.exceptions.ConnectionError as exc:
                raise UserError(_('Could not connect to the Techrar pickup locations API.')) from exc
            except requests.exceptions.RequestException as exc:
                raise UserError(_('Techrar pickup locations request failed: %s') % exc) from exc

            if response.status_code != 200:
                detail = response.text[:1000]
                if response.status_code == 401:
                    raise UserError(_(
                        'Techrar rejected the pickup location credentials (HTTP 401). '
                        'Check the configured API Token and App ID. Details: %s'
                    ) % detail)
                if response.status_code == 403:
                    raise UserError(_(
                        'The Techrar API token cannot read restaurant branches (HTTP 403). '
                        'Ask Techrar to enable access to the restaurant branches API. '
                        'Details: %s'
                    ) % detail)
                raise UserError(_(
                    'Failed to fetch Techrar pickup locations (HTTP %(status)s): %(detail)s',
                    status=response.status_code,
                    detail=detail,
                ))
            try:
                payload = response.json()
            except ValueError as exc:
                raise UserError(_('Techrar returned an invalid pickup locations response.')) from exc

            if page == 1 and isinstance(payload, dict):
                expected_count = payload.get('count')
            items = payload.get('results', []) if isinstance(payload, dict) else payload
            if not isinstance(items, list):
                raise UserError(_('Techrar pickup locations response has an unexpected format.'))
            for item in items:
                if not isinstance(item, dict) or item.get('id') in (None, False, ''):
                    continue
                branch_id = str(item['id'])
                if branch_id in seen_ids:
                    continue
                seen_ids.add(branch_id)
                branch = self.with_context(active_test=False).search([
                    ('techrar_branch_id', '=', branch_id),
                ], limit=1)
                values = self._prepare_location_values(item)
                if branch:
                    branch.write(values)
                    updated += 1
                else:
                    self.create(values)
                    created += 1

            if not isinstance(payload, dict) or not payload.get('next'):
                break
            page += 1
            if page > 1000:
                raise UserError(_('Pickup location pagination exceeded the safety limit.'))

        complete_snapshot = bool(seen_ids) and (
            expected_count is None or expected_count == len(seen_ids)
        )
        missing_branches = self.browse()
        if complete_snapshot:
            missing_branches = self.with_context(active_test=False).search([
                ('synced_from_locations_api', '=', True),
                ('restaurant_id', '=', str(restaurant_id)),
                ('techrar_branch_id', 'not in', list(seen_ids)),
            ])
        if missing_branches:
            missing_branches.write({
                'active': False,
                'techrar_is_active': False,
            })

        config.write({
            'last_branch_sync_at': fields.Datetime.now(),
            'last_branch_sync_count': len(seen_ids),
            'last_branch_sync_status': 'success',
            'last_branch_sync_error': False,
        })
        _logger.info(
            'Techrar pickup locations synced: %s created, %s updated', created, updated,
        )
        return {
            'created': created,
            'updated': updated,
            'archived': len(missing_branches),
            'total': len(seen_ids),
        }

    @api.model
    def _cron_sync_pickup_locations(self):
        configs = self.env['techrar.config'].sudo().search([
            ('auto_branch_sync_enabled', '=', True),
        ])
        for config in configs:
            try:
                with self.env.cr.savepoint():
                    self.sudo()._sync_from_techrar(config)
            except Exception as exc:  # keep the cron running for other companies
                config.write({
                    'last_branch_sync_status': 'failed',
                    'last_branch_sync_error': str(exc)[:2000],
                })
                _logger.exception(
                    'Scheduled Techrar pickup location sync failed for config %s',
                    config.display_name,
                )

    @api.model
    def _prepare_location_values(self, item):
        location = item.get('location') or {}
        if not isinstance(location, dict):
            location = {}
        city = location.get('city') or {}
        if not isinstance(city, dict):
            city = {}
        handler = item.get('handler') or {}
        if not isinstance(handler, dict):
            handler = {}
        handler_user = handler.get('user') or {}
        if not isinstance(handler_user, dict):
            handler_user = {}

        def value(key, *aliases):
            keys = (key,) + aliases
            for source in (item, location):
                for candidate in keys:
                    if source.get(candidate) not in (None, ''):
                        return source[candidate]
            return False

        deleted = bool(value('is_deleted'))
        remote_active = item.get('is_active')
        remote_active = True if remote_active is None else bool(remote_active)
        name_ar = value('name_ar', 'branch_name_ar')
        name_en = value('name_en', 'branch_name_en')
        return {
            'name': name_ar or name_en or _('Unnamed Branch'),
            'branch_name_en': name_en,
            'techrar_branch_id': str(item['id']),
            'techrar_location_id': self._string_value(location.get('id')),
            'city_id': self._string_value(city.get('id')),
            'city_name_en': value('city_name_en') or city.get('name_en'),
            'city_name_ar': value('city_name_ar') or city.get('name_ar'),
            'country_code': city.get('country_code'),
            'city_keywords': city.get('keywords'),
            'city_is_supported': bool(city.get('is_supported')),
            'country_id_techrar': self._string_value(city.get('country')),
            'location_url': value('location_url'),
            'latitude': self._string_value(value('latitude')),
            'longitude': self._string_value(value('longitude')),
            'address1': value('address1'),
            'address2': value('address2'),
            'formatted_address': value('formatted_address'),
            'district': value('district'),
            'district_ar': value('district_ar'),
            'route': value('route'),
            'street_number': self._string_value(value('street_number')),
            'postal_code': self._string_value(value('postal_code')),
            'place_id': value('place_id'),
            'zone_id': self._string_value(value('zone')),
            'app_id': self._string_value(value('app_id')),
            'restaurant_id': self._string_value(item.get('restaurant')),
            'ordering': value('ordering') or 0,
            'branch_hours': self._string_value(item.get('branch_hours')),
            'techrar_is_active': remote_active,
            'is_main': bool(item.get('is_main')),
            'is_dispatch': bool(item.get('is_dispatch')),
            'gender': self._string_value(item.get('gender')),
            'on_demand_opened': bool(item.get('on_demand_opened')),
            'on_demand_delivery_price': item.get('on_demand_delivery_price') or 0.0,
            'on_demand_min_charge': item.get('on_demand_min_charge') or 0.0,
            'handler_id_techrar': self._string_value(handler.get('id')),
            'handler_user_id_techrar': self._string_value(handler_user.get('id')),
            'handler_name': handler_user.get('name'),
            'handler_username': handler_user.get('username'),
            'handler_email': handler_user.get('email'),
            'handler_mobile': handler.get('mobile_number'),
            'handler_is_active': bool(handler.get('is_active')),
            'handler_is_manager': bool(handler.get('is_manager')),
            'techrar_pickup_handler_only': bool(handler.get('pickup_handler_only')),
            'is_synced': bool(value('is_synced')),
            'techrar_is_deleted': deleted,
            'techrar_created_at': self._parse_api_datetime(value('created_at')),
            'techrar_modified_at': self._parse_api_datetime(value('modified_at')),
            'raw_payload': json.dumps(item, ensure_ascii=False, indent=2, default=str),
            'synced_from_locations_api': True,
            'last_seen_at': fields.Datetime.now(),
            'active': not deleted and remote_active,
        }

    @staticmethod
    def _string_value(value):
        return False if value in (None, False, '') else str(value)

    @staticmethod
    def _normalize_bearer_token(value):
        token = (value or '').strip()
        if token.lower().startswith('bearer '):
            token = token[7:].strip()
        return token

    @staticmethod
    def _parse_api_datetime(value):
        if not value:
            return False
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return fields.Datetime.to_string(parsed)
        except (TypeError, ValueError):
            _logger.warning('Could not parse Techrar datetime value %r', value)
            return False
