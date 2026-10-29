from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestMobileNotifications(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env["hr.employee"].create({"name": "Notification Manager"})
        cls.employee = cls.env["hr.employee"].create({
            "name": "Notification Employee", "parent_id": cls.manager.id,
        })
        cls.manager_identity = cls.env["alezdhar.mobile.identity"].create({
            "employee_id": cls.manager.id, "login_identifier": "notify.manager",
        })
        cls.employee_identity = cls.env["alezdhar.mobile.identity"].create({
            "employee_id": cls.employee.id, "login_identifier": "notify.employee",
        })
        cls.manager_identity._set_secret("123456")
        cls.employee_identity._set_secret("123456")

    def test_campaign_to_all_active_mobile_employees(self):
        campaign = self.env["alezdhar.mobile.notification.campaign"].create({
            "name": "Policy update", "title": "Important", "body": "Read the new policy.",
        })
        campaign.action_send()
        self.assertEqual(campaign.state, "sent")
        self.assertEqual(campaign.recipient_count, 2)
        self.assertEqual(self.env["alezdhar.mobile.notification.inbox"].search_count([
            ("campaign_id", "=", campaign.id)
        ]), 2)

    def test_future_campaign_is_scheduled_without_creating_inbox(self):
        campaign = self.env["alezdhar.mobile.notification.campaign"].create({
            "name": "Scheduled policy", "title": "Later", "body": "Not yet",
            "scheduled_at": fields.Datetime.now() + timedelta(hours=1),
        })
        campaign.action_send()
        self.assertEqual(campaign.state, "scheduled")
        self.assertFalse(self.env["alezdhar.mobile.notification.inbox"].search([
            ("campaign_id", "=", campaign.id)
        ]))

    def test_correction_notifies_manager_and_result_notifies_employee(self):
        now = fields.Datetime.now()
        attendance = self.env["hr.attendance"].create({
            "employee_id": self.employee.id,
            "check_in": now - timedelta(hours=8), "check_out": now,
        })
        correction = self.env["alezdhar.attendance.correction"].create({
            "employee_id": self.employee.id, "attendance_id": attendance.id,
            "requested_check_in": now - timedelta(hours=9),
            "requested_check_out": now, "reason": "Device offline",
        })
        Inbox = self.env["alezdhar.mobile.notification.inbox"]
        self.assertEqual(Inbox.search_count([
            ("identity_id", "=", self.manager_identity.id),
            ("category", "=", "correction_submitted"),
        ]), 1)
        correction.mobile_review(self.manager, "approve", "Approved")
        self.assertEqual(Inbox.search_count([
            ("identity_id", "=", self.employee_identity.id),
            ("category", "=", "correction_result"),
        ]), 1)
