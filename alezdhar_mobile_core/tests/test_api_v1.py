import json
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestMobileApiV1(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "alezdhar_mobile.api_enabled", "True"
        )
        cls.employee_a = cls.env["hr.employee"].create(
            {"name": "API Foundation Employee A", "job_title": "Tester A"}
        )
        cls.employee_b = cls.env["hr.employee"].create(
            {"name": "API Foundation Employee B", "job_title": "Tester B"}
        )
        cls.identity_a = cls.env["alezdhar.mobile.identity"].create(
            {"employee_id": cls.employee_a.id, "login_identifier": "api.employee.a"}
        )
        cls.identity_b = cls.env["alezdhar.mobile.identity"].create(
            {"employee_id": cls.employee_b.id, "login_identifier": "api.employee.b"}
        )
        cls.identity_a._set_secret("api-foundation-secret-a")
        cls.identity_b._set_secret("api-foundation-secret-b")
        cls.device_a = cls.env["alezdhar.mobile.device"].create(
            {
                "identity_id": cls.identity_a.id,
                "name": "API Test Android A",
                "installation_id": "api-foundation-device-a",
                "platform": "android",
            }
        )
        now = fields.Datetime.now()
        _session, cls.access_token_a, _refresh = cls.env[
            "alezdhar.mobile.session"
        ].issue(
            cls.identity_a,
            cls.device_a,
            now + timedelta(minutes=15),
            now + timedelta(days=30),
        )

    @staticmethod
    def _payload(response):
        return json.loads(response.content.decode("utf-8"))

    def test_health_is_public_and_safe(self):
        response = self.url_open("/alezdhar/api/v1/health")
        self.assertEqual(response.status_code, 200)
        payload = self._payload(response)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["api_version"], "v1")
        self.assertNotIn("database", payload["data"])

    def test_bootstrap_requires_bearer_token(self):
        response = self.url_open("/alezdhar/api/v1/bootstrap")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self._payload(response)["error"]["code"], "authentication_required"
        )

    def test_bootstrap_returns_only_bound_identity(self):
        response = self.url_open(
            "/alezdhar/api/v1/bootstrap",
            headers={"Authorization": f"Bearer {self.access_token_a}"},
        )
        self.assertEqual(response.status_code, 200)
        profile = self._payload(response)["data"]["profile"]
        self.assertEqual(profile["employee_ref"], self.employee_a.id)
        self.assertNotEqual(profile["employee_ref"], self.employee_b.id)

    def test_me_ignores_guessed_employee_identifier(self):
        response = self.url_open(
            f"/alezdhar/api/v1/me?employee_id={self.employee_b.id}",
            headers={"Authorization": f"Bearer {self.access_token_a}"},
        )
        self.assertEqual(response.status_code, 200)
        profile = self._payload(response)["data"]
        self.assertEqual(profile["employee_ref"], self.employee_a.id)
        self.assertNotEqual(profile["name"], self.employee_b.name)

    def test_revoked_device_token_is_denied(self):
        self.device_a.action_revoke()
        response = self.url_open(
            "/alezdhar/api/v1/me",
            headers={"Authorization": f"Bearer {self.access_token_a}"},
        )
        self.assertEqual(response.status_code, 401)

    def test_authentication_and_activation_remain_disabled(self):
        for path in ("/auth/login", "/auth/activate"):
            response = self.url_open(
                "/alezdhar/api/v1" + path,
                data=b"{}",
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, 503)

    def test_password_login_returns_token_for_bound_employee(self):
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param("alezdhar_mobile.auth_provider", "password")
        try:
            response = self.url_open(
                "/alezdhar/api/v1/auth/login",
                data=json.dumps(
                    {
                        "login_identifier": "api.employee.a",
                        "password": "api-foundation-secret-a",
                        "installation_id": "d34e9d32-6189-42dd-a45d-b6f8ec603c1f",
                        "platform": "android",
                        "device_name": "HTTP Test Android",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, 200)
            data = self._payload(response)["data"]
            self.assertGreater(len(data["access_token"]), 32)
            self.assertEqual(data["profile"]["employee_ref"], self.employee_a.id)
            self.assertNotEqual(data["profile"]["employee_ref"], self.employee_b.id)
        finally:
            parameters.set_param("alezdhar_mobile.auth_provider", "disabled")

    def test_password_login_rejects_unknown_employee(self):
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param("alezdhar_mobile.auth_provider", "password")
        try:
            response = self.url_open(
                "/alezdhar/api/v1/auth/login",
                data=json.dumps(
                    {
                        "login_identifier": "unknown.employee",
                        "password": "not-a-valid-secret",
                        "installation_id": "1af3482b-c6bd-4a35-a77a-0a4c02f606e1",
                        "platform": "android",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(response.status_code, 401)
            self.assertEqual(self._payload(response)["error"]["code"], "invalid_credentials")
        finally:
            parameters.set_param("alezdhar_mobile.auth_provider", "disabled")

