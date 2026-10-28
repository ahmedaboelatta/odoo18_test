import json
from datetime import datetime, timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestAttendanceCorrectionApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("alezdhar_mobile.api_enabled", "True")
        cls.manager = cls.env["hr.employee"].create({"name": "Correction API Manager"})
        cls.employee = cls.env["hr.employee"].create({
            "name": "Correction API Employee", "parent_id": cls.manager.id,
        })
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
        cls.manager_identity = cls.env["alezdhar.mobile.identity"].create({
            "employee_id": cls.manager.id, "login_identifier": "correction.api.manager"
        })
        cls.manager_identity._set_secret("correction-manager-secret")
        cls.manager_device = cls.env["alezdhar.mobile.device"].create({
            "identity_id": cls.manager_identity.id, "name": "Manager Device",
            "installation_id": "correction-manager-device", "platform": "android",
        })
        _session, cls.manager_token, _refresh = cls.env["alezdhar.mobile.session"].issue(
            cls.manager_identity, cls.manager_device, now + timedelta(hours=1), now + timedelta(days=1)
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
        self.assertEqual(response.status_code, 201, response.content)
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

    def test_direct_manager_can_list_and_approve_request(self):
        created = self._json(self._post(self.attendance))["data"]
        listing = self.url_open(
            "/alezdhar/api/v1/attendance/corrections/team",
            headers={"Authorization": f"Bearer {self.manager_token}"},
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(self._json(listing)["data"]["items"][0]["employee_name"], self.employee.name)
        requested_in = datetime.fromisoformat(created["requested_check_in"])
        reviewed = self.url_open(
            f"/alezdhar/api/v1/attendance/corrections/{created['id']}/review",
            data=json.dumps({"decision": "approve", "note": "Approved by direct manager"}).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.manager_token}", "Content-Type": "application/json"},
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.content)
        self.assertEqual(self._json(reviewed)["data"]["state"], "approved")
        self.assertEqual(self.attendance.check_in, requested_in)

    def test_non_manager_cannot_review_and_rejection_requires_note(self):
        created = self._json(self._post(self.attendance))["data"]
        denied = self.url_open(
            f"/alezdhar/api/v1/attendance/corrections/{created['id']}/review",
            data=json.dumps({"decision": "approve"}).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        self.assertEqual(denied.status_code, 404)
        rejected_without_note = self.url_open(
            f"/alezdhar/api/v1/attendance/corrections/{created['id']}/review",
            data=json.dumps({"decision": "reject"}).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.manager_token}", "Content-Type": "application/json"},
        )
        self.assertEqual(rejected_without_note.status_code, 422)
