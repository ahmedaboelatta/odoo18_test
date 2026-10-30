import json
from datetime import date, timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestLeaveApprovalApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("alezdhar_mobile.api_enabled", "True")
        cls.manager = cls.env["hr.employee"].create({"name": "Leave Manager"})
        cls.employee = cls.env["hr.employee"].create({
            "name": "Leave Employee", "parent_id": cls.manager.id,
        })
        cls.outsider = cls.env["hr.employee"].create({"name": "Leave Outsider"})
        cls.leave_type = cls.env["hr.leave.type"].create({
            "name": "Mobile Approval Leave", "requires_allocation": "no",
            "leave_validation_type": "manager",
        })
        today = date.today() + timedelta(days=30)
        while today.weekday() != 0:
            today += timedelta(days=1)
        cls.leave = cls.env["hr.leave"].sudo().create({
            "employee_id": cls.employee.id,
            "holiday_status_id": cls.leave_type.id,
            "request_date_from": today,
            "request_date_to": today,
            "notes": "Mobile approval test",
        })
        now = fields.Datetime.now()
        cls.manager_token = cls._token(cls.manager, "leave-manager", now)
        cls.outsider_token = cls._token(cls.outsider, "leave-outsider", now)

    @classmethod
    def _token(cls, employee, login, now):
        identity = cls.env["alezdhar.mobile.identity"].create({
            "employee_id": employee.id, "login_identifier": login,
            "state": "active",
        })
        device = cls.env["alezdhar.mobile.device"].create({
            "identity_id": identity.id, "name": login,
            "installation_id": login, "platform": "android",
        })
        return cls.env["alezdhar.mobile.session"].issue(
            identity, device, now + timedelta(hours=1), now + timedelta(days=1)
        )[1]

    @staticmethod
    def _json(response):
        return json.loads(response.content.decode("utf-8"))

    def test_direct_manager_can_list_and_approve(self):
        listing = self.url_open(
            "/alezdhar/api/v1/leave/requests/team",
            headers={"Authorization": f"Bearer {self.manager_token}"},
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(self._json(listing)["data"]["items"][0]["id"], self.leave.id)
        reviewed = self.url_open(
            f"/alezdhar/api/v1/leave/requests/{self.leave.id}/review",
            data=json.dumps({"decision": "approve"}).encode(),
            headers={"Authorization": f"Bearer {self.manager_token}", "Content-Type": "application/json"},
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.content)
        self.assertEqual(self._json(reviewed)["data"]["state"], "validate")

    def test_non_manager_cannot_review(self):
        response = self.url_open(
            f"/alezdhar/api/v1/leave/requests/{self.leave.id}/review",
            data=json.dumps({"decision": "approve"}).encode(),
            headers={"Authorization": f"Bearer {self.outsider_token}", "Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 404)

    def test_rejection_requires_reason(self):
        response = self.url_open(
            f"/alezdhar/api/v1/leave/requests/{self.leave.id}/review",
            data=json.dumps({"decision": "reject"}).encode(),
            headers={"Authorization": f"Bearer {self.manager_token}", "Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 422)

    def test_owner_and_manager_can_download_attachment(self):
        attachment = self.env["ir.attachment"].sudo().create({
            "name": "proof.txt", "datas": "cHJvb2Y=", "mimetype": "text/plain",
            "res_model": "hr.leave", "res_id": self.leave.id,
        })
        employee_token = self._token(self.employee, "leave-employee", fields.Datetime.now())
        for token in (employee_token, self.manager_token):
            response = self.url_open(
                f"/alezdhar/api/v1/leave/attachments/{attachment.id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"proof")
        denied = self.url_open(
            f"/alezdhar/api/v1/leave/attachments/{attachment.id}",
            headers={"Authorization": f"Bearer {self.outsider_token}"},
        )
        self.assertEqual(denied.status_code, 404)
