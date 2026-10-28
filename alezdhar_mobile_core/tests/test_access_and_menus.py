from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user


class TestAccessAndMenus(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.company_a.copy({"name": "Foundation Company B"})
        cls.admin_a = new_test_user(
            cls.env,
            login="foundation.mobile.admin.a",
            groups="base.group_user,alezdhar_mobile_core.group_mobile_admin",
            company_id=cls.company_a.id,
        )
        cls.admin_a.company_ids = [Command.set(cls.company_a.ids)]
        cls.auditor_a = new_test_user(
            cls.env,
            login="foundation.mobile.auditor.a",
            groups="base.group_user,alezdhar_mobile_core.group_mobile_auditor",
            company_id=cls.company_a.id,
        )
        cls.employee_a = cls.env["hr.employee"].create(
            {"name": "Company A Employee", "company_id": cls.company_a.id}
        )
        cls.employee_b = cls.env["hr.employee"].create(
            {"name": "Company B Employee", "company_id": cls.company_b.id}
        )
        cls.identity_a = cls.env["alezdhar.mobile.identity"].create(
            {"employee_id": cls.employee_a.id, "login_identifier": "company.a.employee"}
        )
        cls.identity_b = cls.env["alezdhar.mobile.identity"].create(
            {"employee_id": cls.employee_b.id, "login_identifier": "company.b.employee"}
        )

    def test_admin_only_sees_allowed_company_identities(self):
        identities = self.env["alezdhar.mobile.identity"].with_user(self.admin_a).search([])
        self.assertIn(self.identity_a, identities)
        self.assertNotIn(self.identity_b, identities)

    def test_regular_internal_user_has_no_mobile_identity_access(self):
        regular_user = new_test_user(
            self.env,
            login="foundation.regular.user",
            groups="base.group_user",
            company_id=self.company_a.id,
        )
        with self.assertRaises(AccessError):
            self.env["alezdhar.mobile.identity"].with_user(regular_user).search([])

    def test_mobile_admin_menu_and_actions_exist(self):
        root = self.env.ref("alezdhar_mobile_core.menu_mobile_root")
        self.assertTrue(root.active)
        self.assertEqual(root.name, "Alezdhar Mobile")
        for xml_id in (
            "alezdhar_mobile_core.action_mobile_identity",
            "alezdhar_mobile_core.action_mobile_device",
            "alezdhar_mobile_core.action_mobile_feature",
            "alezdhar_mobile_core.action_mobile_audit",
        ):
            self.assertTrue(self.env.ref(xml_id).exists())

        admin_visible = self.env["ir.ui.menu"].with_user(self.admin_a)._visible_menu_ids()
        auditor_visible = self.env["ir.ui.menu"].with_user(
            self.auditor_a
        )._visible_menu_ids()
        self.assertIn(root.id, admin_visible)
        self.assertIn(root.id, auditor_visible)
        self.assertIn(
            self.env.ref("alezdhar_mobile_core.menu_mobile_audit").id,
            auditor_visible,
        )
        self.assertNotIn(
            self.env.ref("alezdhar_mobile_core.menu_mobile_security").id,
            auditor_visible,
        )

    def test_audit_is_immutable(self):
        audit = self.env["alezdhar.mobile.audit"].sudo().create(
            {
                "identity_id": self.identity_a.id,
                "company_id": self.company_a.id,
                "event_type": "foundation.test",
                "outcome": "success",
            }
        )
        with self.assertRaises(UserError):
            audit.write({"outcome": "error"})
        with self.assertRaises(UserError):
            audit.unlink()

