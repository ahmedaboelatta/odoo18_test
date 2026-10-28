import uuid
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessDenied, ValidationError

from odoo.addons.alezdhar_mobile_attendance.models.attendance import AttendanceDenied
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMobileAttendance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "Mobile Attendance Employee"})
        cls.identity = cls.env["alezdhar.mobile.identity"].create(
            {"employee_id": cls.employee.id, "login_identifier": "attendance.employee"}
        )
        cls.identity._set_secret("attendance-test-secret")
        cls.device = cls.env["alezdhar.mobile.device"].create({
            "identity_id": cls.identity.id, "name": "Test Android",
            "installation_id": "attendance-test-device", "platform": "android",
        })
        now = fields.Datetime.now()
        cls.session, _access, _refresh = cls.env["alezdhar.mobile.session"].issue(
            cls.identity, cls.device, now + timedelta(hours=1), now + timedelta(days=1)
        )
        cls.location = cls.env["alezdhar.work.location"].create({
            "name": "Test Branch", "latitude": 24.7136, "longitude": 46.6753,
            "radius_m": 200, "maximum_accuracy_m": 50,
        })
        cls.policy = cls.env["alezdhar.attendance.policy"].create({
            "name": "On-site", "attendance_mode": "on_site", "require_geofence": True,
            "maximum_accuracy_m": 50,
        })
        cls.assignment = cls.env["alezdhar.employee.attendance.assignment"].create({
            "employee_id": cls.employee.id, "policy_id": cls.policy.id,
            "location_ids": [(6, 0, cls.location.ids)], "date_from": fields.Date.today(),
        })

    def _payload(self, **overrides):
        values = {
            "request_id": str(uuid.uuid4()), "latitude": 24.7136, "longitude": 46.6753,
            "accuracy_m": 10, "captured_at": "2000-01-01T00:00:00", "attendance_mode": "on_site",
        }
        values.update(overrides)
        return values

    def test_server_time_is_authoritative_and_checkout_closes_record(self):
        check_in, duplicate = self.env["alezdhar.attendance.event"].mobile_punch(
            self.session, "check_in", self._payload()
        )
        self.assertFalse(duplicate)
        self.assertNotEqual(check_in.server_time.year, 2000)
        self.assertFalse(check_in.attendance_id.check_out)
        check_out, _duplicate = self.env["alezdhar.attendance.event"].mobile_punch(
            self.session, "check_out", self._payload()
        )
        self.assertEqual(check_out.attendance_id, check_in.attendance_id)
        self.assertTrue(check_out.attendance_id.check_out)

    def test_idempotent_request_does_not_create_second_attendance(self):
        payload = self._payload()
        first, duplicate = self.env["alezdhar.attendance.event"].mobile_punch(self.session, "check_in", payload)
        second, duplicate = self.env["alezdhar.attendance.event"].mobile_punch(self.session, "check_in", payload)
        self.assertTrue(duplicate)
        self.assertEqual(first, second)

    def test_outside_geofence_is_denied(self):
        with self.assertRaises(AttendanceDenied) as caught:
            self.env["alezdhar.attendance.event"].mobile_punch(
                self.session, "check_in", self._payload(latitude=25.0, longitude=47.0)
            )
        self.assertEqual(caught.exception.code, "outside_geofence")

    def test_low_accuracy_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["alezdhar.attendance.event"].mobile_punch(
                self.session, "check_in", self._payload(accuracy_m=100)
            )

    def test_checkout_without_open_attendance_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["alezdhar.attendance.event"].mobile_punch(self.session, "check_out", self._payload())

    def test_assignment_is_required(self):
        self.assignment.active = False
        with self.assertRaises(AccessDenied):
            self.env["alezdhar.attendance.event"].mobile_punch(self.session, "check_in", self._payload())

    def test_event_is_immutable(self):
        event, _duplicate = self.env["alezdhar.attendance.event"].mobile_punch(
            self.session, "check_in", self._payload()
        )
        with self.assertRaises(AccessDenied):
            event.with_user(self.env.ref("base.user_admin")).write({"accuracy_m": 1})

    def test_biometric_provider_remains_disabled(self):
        self.assertEqual(self.policy.biometric_provider, "disabled")

    def test_overnight_shift_end_is_next_day(self):
        self.policy.write({"timezone": "Asia/Riyadh", "shift_start_hour": 22.0, "shift_end_hour": 6.0})
        _local, start, end = self.env["alezdhar.attendance.event"]._shift_bounds(
            self.policy, fields.Datetime.to_datetime("2026-10-28 20:00:00")
        )
        self.assertEqual(start.hour, 22)
        self.assertEqual(end.hour, 6)
        self.assertEqual((end.date() - start.date()).days, 1)

    def test_receipt_contains_exact_times_and_duration(self):
        check_in, _duplicate = self.env["alezdhar.attendance.event"].mobile_punch(
            self.session, "check_in", self._payload()
        )
        check_out, _duplicate = self.env["alezdhar.attendance.event"].mobile_punch(
            self.session, "check_out", self._payload()
        )
        receipt = check_out.receipt_dto()
        self.assertTrue(receipt["check_in"])
        self.assertTrue(receipt["check_out"])
        self.assertGreaterEqual(receipt["worked_minutes"], 0)
        self.assertIn(receipt["punctuality_status"], ("normal", "early_leave"))

    def test_remote_mode_does_not_require_geofence(self):
        self.policy.write({"attendance_mode": "remote", "require_geofence": True})
        event, duplicate = self.env["alezdhar.attendance.event"].mobile_punch(
            self.session, "check_in", self._payload(
                latitude=25.0, longitude=47.0, attendance_mode="remote"
            )
        )
        self.assertFalse(duplicate)
        self.assertEqual(event.geofence_outcome, "not_required")
        self.assertFalse(event.location_id)

    def test_report_has_one_row_for_check_in_and_out(self):
        check_in, _duplicate = self.env["alezdhar.attendance.event"].mobile_punch(
            self.session, "check_in", self._payload()
        )
        self.env["alezdhar.attendance.event"].mobile_punch(
            self.session, "check_out", self._payload()
        )
        self.env.flush_all()
        row = self.env["alezdhar.attendance.report"].search(
            [("id", "=", check_in.attendance_id.id)]
        )
        self.assertEqual(len(row), 1)
        self.assertTrue(row.check_out)
        self.assertGreaterEqual(row.overtime_hours, 0)

    def test_approved_correction_updates_attendance_and_keeps_original_audit(self):
        event, _duplicate = self.env["alezdhar.attendance.event"].mobile_punch(
            self.session, "check_in", self._payload()
        )
        original = event.attendance_id.check_in
        requested = original - timedelta(minutes=10)
        correction = self.env["alezdhar.attendance.correction"].create({
            "employee_id": self.employee.id,
            "attendance_id": event.attendance_id.id,
            "requested_check_in": requested,
            "reason": "GPS delay",
        })
        correction.action_approve()
        self.assertEqual(correction.state, "approved")
        self.assertEqual(correction.original_check_in, original)
        self.assertEqual(event.attendance_id.check_in, requested)

    def test_rejected_correction_requires_reason(self):
        event, _duplicate = self.env["alezdhar.attendance.event"].mobile_punch(
            self.session, "check_in", self._payload()
        )
        correction = self.env["alezdhar.attendance.correction"].create({
            "employee_id": self.employee.id,
            "attendance_id": event.attendance_id.id,
            "requested_check_in": event.attendance_id.check_in,
            "reason": "Wrong time",
        })
        with self.assertRaises(ValidationError):
            correction.action_reject()
