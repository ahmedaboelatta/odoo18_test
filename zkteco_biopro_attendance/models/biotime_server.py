# -*- coding: utf-8 -*-

from datetime import timedelta
from odoo import api, models, fields, _
import requests
from odoo.exceptions import UserError, ValidationError
from requests.exceptions import HTTPError
from .tools import batch
from urllib.parse import urljoin


class BioTimeServer(models.Model):
    _name = 'biotime.server'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'BioTime Server'

    name = fields.Char(string='Server Name', help='Name of Server ex: UAE company A server', required=True)
    server_ip = fields.Char(help='External IP address', required=True)
    port = fields.Integer(string='Port Number', help='Port to reach server', required=True, default=80)
    admin_username = fields.Char(help='Admin username of the BioTime 8.5 server')
    admin_password = fields.Char(help='Admin password of the BioTime 8.5 server')
    department_code = fields.Char(required=True)
    area_code = fields.Char(required=True)
    tz_offset = fields.Integer('UTC timezone difference', help='ex: +4, -2', required=True)
    active = fields.Boolean(default=True)
    duplicate_threshold = fields.Integer(default=60, help='Number of seconds to consider two punches as duplicates')

    jwt_token = fields.Char()

    last_attendance_sync = fields.Datetime(readonly=False)

    url = fields.Char(compute='_compute_url')

    @api.constrains('active')
    def _constraint_unique_server(self):
        if self.search_count([]) > 1:
            raise ValidationError(_('You can not have more than one active server at a time'))

    @api.depends('server_ip', 'port')
    def _compute_url(self):
        for record in self:
            record.url = 'http://{}:{}'.format(record.server_ip, record.port)

    def get_jwt_token(self, raise_alert=True):
        self.ensure_one()

        headers = {'Content-Type': 'application/json'}
        data = {
            'username': self.admin_username,
            'password': self.admin_password,
        }

        try:
            response = requests.post(urljoin(self.url, '/jwt-api-token-auth/'), json=data, headers=headers, timeout=30)
            response.raise_for_status()
            response = response.json()

            if response.get('token'):
                self.jwt_token = response.get('token')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success !'),
                        'message': _('Connected successfully'),
                        'sticky': True,
                        'type': 'success',
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
            else:
                msg = _('Could not connect to server {}'.format(self.name))

        except Exception as e:
            msg = _('Could not connect to server {}: {}'.format(self.name, e))

        if raise_alert:
            raise UserError(msg)

    @api.model
    def _get_asset_from_server(self, asset_type='employee', page=1, page_size=100, attendance_list=None):
        if not attendance_list:
            attendance_list = []
        headers = self._generate_jwt_headers(self.jwt_token) 

        endpoint = '/personnel/api/employees/'
        query_params = '?page={}&page_size={}'.format(page, page_size)

        if asset_type == 'transaction':
            endpoint = '/iclock/api/transactions/'

            # only query fingerprint punches not already synced
            # Timezone timedelta manipulation. On odoo time is stored in UTC whereas on biotime it will be local time
            if self.last_attendance_sync:
                biotime_last_attendance_sync = self.last_attendance_sync + timedelta(hours=self.tz_offset)
                request_start_time = biotime_last_attendance_sync.strftime('%Y-%m-%d+%H:%M:%S')
                query_params += '&start_time={}'.format(request_start_time)

        try:
            response = requests.get(self.url + endpoint + query_params, headers=headers, timeout=30)
            response.raise_for_status()
            response = response.json()

            if response.get('data'):
                attendance_list += response.get('data')

            # recursively get all attendances across pages
            if response.get('next'):
                attendance_list = self._get_asset_from_server(asset_type, page + 1, page_size, attendance_list)
        except HTTPError as e:
            self.message_post(body=_('Error when trying to get assets:\n %s') % str(e))
        except Exception as e:
            self.message_post(body=_('Error when trying to get %s records:\n %s') % (asset_type, str(e)))

        return attendance_list

    def _generate_jwt_headers(self, jwt_token):
        return {
            'Authorization': 'JWT {}'.format(jwt_token), 'Content-Type': 'application/json'
        }

    def _add_to_biotime_server(self, employee_ids):
        """
        Send new employees to the biotime server. Function called by a cron
        """
        self.ensure_one()

        self.get_jwt_token(raise_alert=False)
        headers = self._generate_jwt_headers(self.jwt_token) 

        filtered_employee_ids = employee_ids.filtered(lambda e: e.zk_emp_code)

        for employee_batch in batch(filtered_employee_ids):
            for employee in employee_batch:
                data = {
                    'emp_code': employee.zk_emp_code,
                    'department': self.department_code,
                    'area': [self.area_code],
                    'first_name': employee.name,
                    'mobile': employee.mobile_phone if employee.mobile_phone else '',
                    'email': employee.work_email if employee.work_email else '',
                }

                try:
                    url = self.url + '/personnel/api/employees/'
                    response = requests.post(url, json=data, headers=headers, timeout=30)
                    response.raise_for_status()

                    if response.status_code == 201:
                        response_json = response.json()
                        self.zk_emp_id = response_json.get('id')

                except HTTPError as e:
                    self.message_post(body='Error when trying to create an employee:\n %s' % str(e))
                    break  # issue is with the server so we stop the syncing
                except Exception as e:
                    employee.message_post(body='Error when trying to create an employee on biotime:\n %s' % str(e))
            self.env.cr.commit()

    def _remove_from_biotime_server(self, zk_emp_id):
        """
        Delete the employee on the biotime server. Do not call this function in a cron
        """
        self.ensure_one()

        self.get_jwt_token(raise_alert=False)
        headers = self._generate_jwt_headers(self.jwt_token) 

        url = self.url + '/personnel/api/employees/{}/'.format(zk_emp_id)
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
