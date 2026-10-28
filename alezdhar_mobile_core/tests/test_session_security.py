from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessDenied, ValidationError
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

    def test_device_from_another_identity_is_rejected(self):
        other_employee = self.env["hr.employee"].create({"name": "Other Employee"})
        other_identity = self.env["alezdhar.mobile.identity"].create(
            {"employee_id": other_employee.id, "login_identifier": "other.employee"}
        )
        other_identity._set_secret("other-foundation-secret")
        now = fields.Datetime.now()
        with self.assertRaises(ValidationError):
            self.env["alezdhar.mobile.session"].sudo().create(
                {
                    "identity_id": other_identity.id,
                    "device_id": self.device.id,
                    "access_token_hash": "a" * 64,
                    "access_expires_at": now + timedelta(minutes=15),
                    "refresh_token_hash": "b" * 64,
                    "refresh_expires_at": now + timedelta(days=30),
                }
            )

    def test_refresh_token_is_rotated_and_cannot_be_reused(self):
        old_session, _access_token, refresh_token = self._issue()
        now = fields.Datetime.now()
        new_session, new_access, new_refresh = self.env["alezdhar.mobile.session"].rotate_refresh_token(
            refresh_token, now + timedelta(minutes=15), now + timedelta(days=30)
        )
        self.assertTrue(old_session.revoked_at)
        self.assertNotEqual(new_session, old_session)
        self.assertEqual(
            self.env["alezdhar.mobile.session"].authenticate_access_token(new_access), new_session
        )
        self.assertEqual(
            self.env["alezdhar.mobile.session"].authenticate_refresh_token(new_refresh), new_session
        )
        with self.assertRaises(AccessDenied):
            self.env["alezdhar.mobile.session"].authenticate_refresh_token(refresh_token)
