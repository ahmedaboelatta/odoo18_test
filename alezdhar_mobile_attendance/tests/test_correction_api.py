import json
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestAttendanceCorrectionApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("alezdhar_mobile.api_enabled", "True")
        cls.employee = cls.env["hr.employee"].create({"name": "Correction API Employee"})
        cls.other_employee = cls.env["hr.employee"].create({"name": "Other Correction Employee"})
        cls.identity = cls.env["alezdhar.mobile.identity"].create({
            "employee_id": cls.employee.id, "login_identifier": "correction.api.employee"
        })
        cls.identity._set_secret("correction-api-secret")
        cls.device = cls.env["alezdhar.mobile.device"].create({
            "identity_id": cls.identity.id, "name": "Correction Test Device",
            "installation_id": "correction-api-device", "platform": "android",
        })
        now = fields.Datetime.now()
        _session, cls.token, _refresh = cls.env["alezdhar.mobile.session"].issue(
            cls.identity, cls.device, now + timedelta(hours=1), now + timedelta(days=1)
        )
        cls.attendance = cls.env["hr.attendance"].create({
            "employee_id": cls.employee.id, "check_in": now - timedelta(hours=8), "check_out": now,
        })
        cls.other_attendance = cls.env["hr.attendance"].create({
            "employee_id": cls.other_employee.id, "check_in": now - timedelta(hours=8), "check_out": now,
        })

    @staticmethod
    def _json(response):
        return json.loads(response.content.decode("utf-8"))

    def _post(self, attendance):
        return self.url_open(
            "/alezdhar/api/v1/attendance/corrections",
            data=json.dumps({
                "attendance_ref": attendance.id,
                "requested_check_in": (attendance.check_in - timedelta(minutes=10)).isoformat(),
                "requested_check_out": attendance.check_out.isoformat(),
                "reason": "Device was temporarily offline",
            }).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )

    def test_employee_can_submit_and_list_own_correction(self):
        response = self._post(self.attendance)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self._json(response)["data"]["state"], "submitted")
        listing = self.url_open(
            "/alezdhar/api/v1/attendance/corrections",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(self._json(listing)["data"]["items"][0]["attendance_ref"], self.attendance.id)

    def test_employee_cannot_submit_for_another_employee(self):
        response = self._post(self.other_attendance)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self._json(response)["error"]["code"], "correction_validation_failed")
