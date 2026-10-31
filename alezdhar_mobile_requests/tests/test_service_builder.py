from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestMobileServiceBuilder(TransactionCase):
    def test_complaint_routes_to_all_responsible_users(self):
        user_a = new_test_user(self.env, login="complaint_a", groups="base.group_user")
        user_b = new_test_user(self.env, login="complaint_b", groups="base.group_user")
        service = self.env["alezdhar.mobile.service"].create({
            "name": "Complaint", "code": "complaint_test",
            "service_type": "complaint", "responsible_user_ids": [(6, 0, [user_a.id, user_b.id])],
        })
        field = self.env["alezdhar.mobile.service.field"].create({
            "service_id": service.id, "label": "Category", "key": "category",
            "field_type": "select", "required": True,
        })
        self.env["alezdhar.mobile.service.field.option"].create({
            "field_id": field.id, "label": "Workplace", "value": "workplace",
        })
        employee = self.env["hr.employee"].create({"name": "Complaint Employee"})
        request = self.env["alezdhar.mobile.service.request"].create({
            "service_id": service.id, "employee_id": employee.id,
            "description": "Confidential complaint",
            "answers_json": {"category": "workplace"},
        })
        self.assertEqual(set(request.assigned_user_ids.ids), {user_a.id, user_b.id})
        activities = self.env["mail.activity"].search([
            ("res_model", "=", request._name), ("res_id", "=", request.id),
        ])
        self.assertEqual(set(activities.user_id.ids), {user_a.id, user_b.id})

    def test_service_state_and_archive(self):
        service = self.env["alezdhar.mobile.service"].create({
            "name": "Draft Service", "code": "draft_service", "state": "draft",
        })
        service.action_publish()
        self.assertEqual(service.state, "published")
        service.toggle_active()
        self.assertFalse(service.active)
