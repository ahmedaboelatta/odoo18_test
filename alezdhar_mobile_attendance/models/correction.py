from odoo import _, fields, models
from odoo.exceptions import ValidationError


class AlezdharAttendanceCorrection(models.Model):
    _name = "alezdhar.attendance.correction"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Attendance Correction Request"
    _order = "create_date desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    attendance_id = fields.Many2one("hr.attendance", required=True, index=True, ondelete="restrict")
    current_check_in = fields.Datetime(related="attendance_id.check_in", readonly=True)
    current_check_out = fields.Datetime(related="attendance_id.check_out", readonly=True)
    requested_check_in = fields.Datetime(required=True)
    requested_check_out = fields.Datetime()
    reason = fields.Text(required=True)
    state = fields.Selection(
        [("submitted", "Submitted"), ("approved", "Approved"), ("rejected", "Rejected")],
        required=True, default="submitted", index=True, readonly=True, tracking=True,
    )
    reviewer_id = fields.Many2one("res.users", readonly=True)
    reviewer_employee_id = fields.Many2one("hr.employee", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    review_note = fields.Text()
    original_check_in = fields.Datetime(readonly=True)
    original_check_out = fields.Datetime(readonly=True)

    def _validate_times(self):
        for record in self:
            if record.requested_check_out and record.requested_check_out <= record.requested_check_in:
                raise ValidationError(_("Requested check-out must be after check-in."))
            if record.attendance_id.employee_id != record.employee_id:
                raise ValidationError(_("The attendance record does not belong to this employee."))

    def action_approve(self):
        self._validate_times()
        for record in self:
            if record.state != "submitted":
                raise ValidationError(_("Only submitted corrections can be approved."))
            original_in, original_out = record.attendance_id.check_in, record.attendance_id.check_out
            record.attendance_id.sudo().write({
                "check_in": record.requested_check_in,
                "check_out": record.requested_check_out,
            })
            record.write({
                "state": "approved", "reviewer_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(), "original_check_in": original_in,
                "original_check_out": original_out,
            })

    def action_reject(self):
        for record in self:
            if record.state != "submitted":
                raise ValidationError(_("Only submitted corrections can be rejected."))
            if not record.review_note:
                raise ValidationError(_("A rejection reason is required."))
            record.write({"state": "rejected", "reviewer_id": self.env.user.id, "reviewed_at": fields.Datetime.now()})

    def mobile_review(self, manager_employee, decision, note=None):
        """Review a direct report's request from the mobile API.

        The controller performs the same ownership check, but it is repeated
        here so a future caller cannot accidentally bypass team isolation.
        """
        self.ensure_one()
        if self.employee_id.parent_id != manager_employee or self.employee_id == manager_employee:
            raise ValidationError(_("Only the employee's direct manager can review this request."))
        if self.state != "submitted":
            raise ValidationError(_("Only submitted corrections can be reviewed."))
        note = (note or "").strip()
        if decision == "reject" and not note:
            raise ValidationError(_("A rejection reason is required."))
        if decision not in ("approve", "reject"):
            raise ValidationError(_("The review decision is invalid."))
        if decision == "approve":
            self._validate_times()
            original_in, original_out = self.attendance_id.check_in, self.attendance_id.check_out
            self.attendance_id.sudo().write({
                "check_in": self.requested_check_in,
                "check_out": self.requested_check_out,
            })
            values = {
                "state": "approved",
                "original_check_in": original_in,
                "original_check_out": original_out,
            }
        else:
            values = {"state": "rejected"}
        values.update({
            "reviewer_employee_id": manager_employee.id,
            "reviewed_at": fields.Datetime.now(),
            "review_note": note or False,
        })
        self.write(values)
        partner = manager_employee.work_contact_id
        self.sudo().message_post(
            body=_("Mobile correction request %(decision)s by %(manager)s.",
                   decision=_("approved") if decision == "approve" else _("rejected"),
                   manager=manager_employee.name),
            author_id=partner.id if partner else None,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

    def unlink(self):
        if any(record.state != "submitted" for record in self):
            raise ValidationError(_("Reviewed correction requests cannot be deleted."))
        return super().unlink()

    def mobile_dto(self):
        self.ensure_one()
        return {
            "id": self.id,
            "attendance_ref": self.attendance_id.id,
            "attendance_check_in": self.current_check_in.isoformat() if self.current_check_in else None,
            "attendance_check_out": self.current_check_out.isoformat() if self.current_check_out else None,
            "requested_check_in": self.requested_check_in.isoformat() if self.requested_check_in else None,
            "requested_check_out": self.requested_check_out.isoformat() if self.requested_check_out else None,
            "reason": self.reason,
            "employee_name": self.employee_id.name,
            "state": self.state,
            "review_note": self.review_note,
            "submitted_at": self.create_date.isoformat() if self.create_date else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }
