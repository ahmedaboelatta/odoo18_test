import pytz
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _

from odoo.exceptions import ValidationError
from datetime import datetime, timedelta

BATCH_SIZE = 100
from collections import defaultdict


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    active = fields.Boolean(default=True, string="Not recorded")
    zkteco_checkout_id = fields.Integer()
    zkteco_checkin_id = fields.Integer()
    server_id = fields.Many2one("biotime.server")
    

    @api.model
    def _get_from_server(self):
        servers = self.env['biotime.server'].search([])
        employees_list = self.env["hr.employee"].search_read(
            [("zk_emp_code", "!=", False)],
            ["id", "zk_emp_code", "company_id"]
        )
        employees_code_id_dict = defaultdict(list)
        for e in employees_list:
            employees_code_id_dict[e.get("zk_emp_code")].append(e.get("id"))

        attendance_zkteco_raw = self.env["hr.attendance"].read_group(
            [
                ('zkteco_checkout_id', '!=', False),
                ('zkteco_checkin_id', '!=', False),
                ('server_id', 'in', servers.ids)
            ],
            ['server_id', 'zkteco_checkin_id:array_agg', 'zkteco_checkout_id:array_agg'],
            ['server_id']
        )
        zkteco_ids_server_dict = {}
        for entry in attendance_zkteco_raw:
            key = entry.get('server_id')[0]
            zkteco_ids_server_dict[key] = entry.get('zkteco_checkin_id', []) + entry.get('zkteco_checkout_id', [])

        for server in servers:
            server.get_jwt_token(raise_alert=False)
            attendance_list = server._get_asset_from_server(asset_type="transaction")

            if not attendance_list:
                continue
            self.env['hr.attendance'].generate_attendance(attendance_list, employees_code_id_dict, zkteco_ids_server_dict, server)

    def generate_attendance(self, attendance_list, employees_code_id_dict, zkteco_ids_server_dict, server):
        # Filter out data
        query_date = fields.Datetime.now()
        attendance_list = [
            a for a in attendance_list if
            a.get("emp_code") in employees_code_id_dict and a.get("punch_time") and a.get(
                "id") not in zkteco_ids_server_dict.get(server.id, [])
        ]

        datetime_format = '%Y-%m-%d %H:%M:%S'

        # sort by punch time - allows to match check in punches with checkouts to create attendance entries
        attendance_list.sort(key=lambda x: datetime.strptime(x["punch_time"], datetime_format))
        employee_attendance = {}
        duplicate_attendance = {}
        bad_vals = []
        processed = 0
        for attendance in attendance_list:
            emp_code = attendance.get("emp_code")
            datetime_format = '%Y-%m-%d %H:%M:%S'
            new_entry = datetime.strptime(attendance.get("punch_time"), datetime_format)

            if prev_punch := employee_attendance.get(attendance.get("emp_code")):
                prev_entry = datetime.strptime(prev_punch.get("punch_time"), datetime_format)
                time_difference = abs((new_entry - prev_entry).total_seconds())
            if attendance.get("punch_state") == "0":
                # check in entry
                if employee_attendance.get(emp_code):
                    if time_difference <= server.duplicate_threshold:
                        bad_vals.append(_("Ignoring duplicate checkin entry in the same minute:\n") + str(employee_attendance[emp_code]))
                    else: 
                        bad_vals.append(_("No matching checkout for checkin:\n") + str(employee_attendance[emp_code]))
                        employee_attendance[emp_code] = attendance
                else:
                    employee_attendance[emp_code] = attendance                   
            else:  # check out entry
                if prev_punch := duplicate_attendance.get(attendance.get("emp_code")):
                    prev_entry = datetime.strptime(prev_punch.get("punch_time"), datetime_format)
                    time_difference_checkout = abs((new_entry - prev_entry).total_seconds())
                if not employee_attendance.get(emp_code):
                    if duplicate_attendance.get(emp_code) and time_difference_checkout < server.duplicate_threshold:
                        bad_vals.append(_("Ignoring duplicate checkout entry in the same minute:\n") + str(duplicate_attendance[emp_code]))
                    else:
                        bad_vals.append(_("No matching checkin for checkout:\n") + str(attendance))
                else:
                    duplicate_attendance[emp_code]=attendance
                    checkout_entry = attendance
                    checkin_entry = employee_attendance.get(emp_code)
                    employee_attendance[emp_code] = False


                    # Timezone timedelta manipulation.
                    # On odoo time is stored in UTC whereas on biotime it will be local time
                    check_in_datetime = datetime.strptime(checkin_entry["punch_time"], '%Y-%m-%d %H:%M:%S')
                    check_out_datetime = datetime.strptime(checkout_entry["punch_time"], '%Y-%m-%d %H:%M:%S')

                    tz_name = self.env.user.tz or 'UTC'
                    tz = pytz.timezone(tz_name)
                    difference = tz.utcoffset(datetime.now()).seconds / 3600
                    check_in_datetime += timedelta(hours=-difference)
                    check_out_datetime += timedelta(hours=-difference)
                    for employee_id in employees_code_id_dict.get(emp_code):
                        vals = {
                            'employee_id': employee_id,
                            'check_in': check_in_datetime,
                            'check_out': check_out_datetime,
                            'zkteco_checkin_id': checkin_entry.get('id'),
                            'zkteco_checkout_id': checkout_entry.get('id'),
                            'server_id': server.id,
                            'active': True,
                        }

                        if self.env["hr.attendance"]._no_overlap(vals):
                            try:
                                self.env['hr.attendance'].with_context(zkteco=True).create(vals)
                            except ValidationError as e:
                                bad_vals.append(str(e) + '\n' + str(vals))
                        else:  # machine/biotime employee code not on odoo OR checkout time AFTER checkin
                            bad_vals.append(_("Existing overlapping attendance:\n") + str(vals))

                        processed += 1
                        if not processed % BATCH_SIZE:
                            # Call message_post before self._cr.commit() to ensure that bad_vals are not lost. In the case of a timeout,
                            # the transaction will rollback and the bad_vals will still be there when you run this function again.
                            if bad_vals:
                                msg = _("Could not write the following values from BioTime server:" + '\n\n- '.join(bad_vals))
                                server.message_post(subject=_("Biotime Error(s)"), body=msg)
                            bad_vals = []
                            self._cr.commit()

        server.last_attendance_sync = query_date
        if bad_vals:
            msg = _("Could not write the following values from BioTime server:" + '\n\n- '.join(bad_vals))
            server.message_post(subject=_("Biotime Error(s)"), body=msg)
        self._cr.commit()

    # Logic adapted from standard
    def _no_overlap(self, val):
        # we take the latest attendance before our check_in time and check it doesn't overlap with ours
        latest_attendance = self.env['hr.attendance'].search([
            ('employee_id', '=', val.get("employee_id")),
            ('check_in', '<=', val.get("check_in")),
        ], order='check_in desc', limit=1)
        if latest_attendance and latest_attendance.check_out and latest_attendance.check_out > val.get("check_in"):
            return False

        if val.get("check_out"):
            # we verify that the latest attendance with check_in time before our check_out time
            # is the same as the one before our check_in time computed before, otherwise it overlaps
            last_attendance_before_check_out = self.env['hr.attendance'].search([
                ('employee_id', '=', val.get("employee_id")),
                ('check_in', '<', val.get("check_out")),
            ], order='check_in desc', limit=1)
            if last_attendance_before_check_out and latest_attendance != last_attendance_before_check_out:
                return False
        return True

    def _cron_close_overdue_attendance(self):
        attendance_ids = self.search([('check_in', '!=', False), ('check_out', '=', False)])
        attendance_to_close = self.env['hr.attendance']
        for attendance in attendance_ids:
            hours_per_day = attendance.employee_id.resource_calendar_id.hours_per_day
            cutoff = attendance.check_in + relativedelta(hours=hours_per_day)
            if cutoff < datetime.now():
                attendance_to_close |= attendance

        attendance_to_close.write({
            'check_out': datetime.now()
        })
