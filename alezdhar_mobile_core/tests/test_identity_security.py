from psycopg2 import IntegrityError

from odoo.exceptions import AccessDenied
from odoo.tests.common import TransactionCase


class TestMobileIdentitySecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee_a = cls.env["hr.employee"].create({"name": "Foundation Employee A"})
        cls.employee_b = cls.env["hr.employee"].create({"name": "Foundation Employee B"})
        cls.identity_a = cls.env["alezdhar.mobile.identity"].create(
            {"employee_id": cls.employee_a.id, "login_identifier": "employee.a"}
        )
        cls.identity_b = cls.env["alezdhar.mobile.identity"].create(
            {"employee_id": cls.employee_b.id, "login_identifier": "employee.b"}
        )
        cls.identity_a._set_secret("correct-horse-battery-staple")
        cls.identity_b._set_secret("another-long-test-secret")

    def test_duplicate_employee_identity_is_blocked(self):
        with self.cr.savepoint():
            with self.assertRaises(IntegrityError):
                self.env["alezdhar.mobile.identity"].create(
                    {
                        "employee_id": self.employee_a.id,
                        "login_identifier": "duplicate.a",
                    }
                )

    def test_login_identifier_is_normalized_without_recursive_write(self):
        employee = self.env["hr.employee"].create({"name": "Normalized Employee"})
        identity = self.env["alezdhar.mobile.identity"].create(
            {"employee_id": employee.id, "login_identifier": "  Employee.Mixed  "}
        )
        self.assertEqual(identity.login_identifier, "employee.mixed")

    def test_secret_is_hashed_and_not_recoverable(self):
        self.assertNotEqual(
            self.identity_a.secret_hash, "correct-horse-battery-staple"
        )
        self.assertTrue(self.identity_a._check_secret("correct-horse-battery-staple"))
        self.assertFalse(self.identity_a._check_secret("wrong-secret-value"))

    def test_secret_hash_fields_cannot_be_written_directly(self):
        with self.assertRaises(AccessDenied):
            self.identity_a.with_context(alezdhar_internal_secret_write=True).write(
                {"secret_hash": "attacker-controlled-hash"}
            )
        with self.assertRaises(AccessDenied):
            self.env["alezdhar.mobile.identity"].create(
                {
                    "employee_id": self.env["hr.employee"].create(
                        {"name": "Injected Secret Employee"}
                    ).id,
                    "login_identifier": "injected.secret",
                    "secret_hash": "attacker-controlled-hash",
                    "secret_salt": "attacker-controlled-salt",
                }
            )

    def test_archived_employee_cannot_authenticate(self):
        self.employee_a.active = False
        with self.assertRaises(AccessDenied):
            self.identity_a._assert_can_authenticate()

    def test_safe_profile_is_bound_to_authenticated_identity(self):
        profile_a = self.identity_a.safe_profile_dto()
        profile_b = self.identity_b.safe_profile_dto()
        self.assertEqual(profile_a["employee_ref"], self.employee_a.id)
        self.assertEqual(profile_b["employee_ref"], self.employee_b.id)
        self.assertNotEqual(profile_a["employee_ref"], profile_b["employee_ref"])

    def test_password_authentication_is_bound_to_employee_identity(self):
        authenticated = self.env["alezdhar.mobile.identity"].authenticate_password(
            "  EMPLOYEE.A  ", "correct-horse-battery-staple"
        )
        self.assertEqual(authenticated.employee_id, self.employee_a)
        self.assertEqual(authenticated.failed_attempts, 0)

    def test_unknown_or_wrong_credentials_are_denied(self):
        with self.assertRaises(AccessDenied):
            self.env["alezdhar.mobile.identity"].authenticate_password(
                "missing.employee", "wrong-secret-value"
            )
        with self.assertRaises(AccessDenied):
            self.env["alezdhar.mobile.identity"].authenticate_password(
                "employee.a", "wrong-secret-value"
            )

