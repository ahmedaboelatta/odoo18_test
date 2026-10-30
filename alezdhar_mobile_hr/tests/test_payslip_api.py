import json
from datetime import date, timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestPayslipApi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("alezdhar_mobile.api_enabled", "True")
        cls.employee = cls.env["hr.employee"].create({"name": "Payslip Owner"})
        cls.other = cls.env["hr.employee"].create({"name": "Other Employee"})
        cls.slip = cls.env["hr.payslip"].sudo().create({
            "name": "Owner payslip", "employee_id": cls.employee.id,
            "date_from": date.today().replace(day=1), "date_to": date.today(), "state": "done",
        })
        cls.other_slip = cls.env["hr.payslip"].sudo().create({
            "name": "Other payslip", "employee_id": cls.other.id,
            "date_from": date.today().replace(day=1), "date_to": date.today(), "state": "done",
        })
        cls.token = cls._token(cls.employee, "payslip-owner")

    @classmethod
    def _token(cls, employee, login):
        identity = cls.env["alezdhar.mobile.identity"].create({
            "employee_id": employee.id, "login_identifier": login, "state": "active",
        })
        device = cls.env["alezdhar.mobile.device"].create({
            "identity_id": identity.id, "name": login, "installation_id": login, "platform": "android",
        })
        now = fields.Datetime.now()
        return cls.env["alezdhar.mobile.session"].issue(
            identity, device, now + timedelta(hours=1), now + timedelta(days=1)
        )[1]

    def test_employee_only_sees_own_done_payslip(self):
        response = self.url_open("/alezdhar/api/v1/payslips", headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in json.loads(response.content)["data"]["items"]]
        self.assertIn(self.slip.id, ids)
        self.assertNotIn(self.other_slip.id, ids)

    def test_other_employee_payslip_is_hidden(self):
        response = self.url_open(
            f"/alezdhar/api/v1/payslips/{self.other_slip.id}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(response.status_code, 404)
