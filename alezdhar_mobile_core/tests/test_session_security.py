from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessDenied
from odoo.tests.common import TransactionCase


class TestMobileSessionSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        employee = cls.env["hr.employee"].create({"name": "Session Employee"})
        cls.identity = cls.env["alezdhar.mobile.identity"].create(
            {"employee_id": employee.id, "login_identifier": "session.employee"}
        )
        cls.identity._set_secret("foundation-session-secret")
        cls.device = cls.env["alezdhar.mobile.device"].create(
            {
                "identity_id": cls.identity.id,
                "name": "Test Android",
                "installation_id": "foundation-test-installation",
                "platform": "android",
            }
        )

    def _issue(self):
        now = fields.Datetime.now()
        return self.env["alezdhar.mobile.session"].issue(
            self.identity,
            self.device,
            now + timedelta(minutes=15),
            now + timedelta(days=30),
        )

    def test_raw_tokens_are_returned_once_and_only_hashes_are_stored(self):
        session, access_token, refresh_token = self._issue()
        self.assertNotEqual(session.access_token_hash, access_token)
        self.assertNotEqual(session.refresh_token_hash, refresh_token)
        authenticated = self.env[
            "alezdhar.mobile.session"
        ].authenticate_access_token(access_token)
        self.assertEqual(authenticated, session)

    def test_revoked_device_revokes_session(self):
        session, access_token, _refresh_token = self._issue()
        self.device.action_revoke()
        self.assertTrue(session.revoked_at)
        with self.assertRaises(AccessDenied):
            self.env["alezdhar.mobile.session"].authenticate_access_token(access_token)

    def test_expired_token_is_denied(self):
        session, access_token, _refresh_token = self._issue()
        session.sudo().access_expires_at = fields.Datetime.now() - timedelta(seconds=1)
        with self.assertRaises(AccessDenied):
            self.env["alezdhar.mobile.session"].authenticate_access_token(access_token)
