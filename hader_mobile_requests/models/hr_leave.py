from odoo import _, fields, models
from odoo.exceptions import ValidationError


class HrLeave(models.Model):
    _inherit = "hr.leave"

    mobile_review_note = fields.Text(readonly=True)
    mobile_reviewed_by_employee_id = fields.Many2one(
        "hr.employee", readonly=True, ondelete="set null"
    )
    mobile_reviewed_at = fields.Datetime(readonly=True)

    def mobile_review(self, manager_employee, decision, note=None):
        self.ensure_one()
        if self.employee_id.parent_id != manager_employee or self.employee_id == manager_employee:
            raise ValidationError(_("Only the employee's direct manager can review this request."))
        if self.state != "confirm":
            raise ValidationError(_("Only requests waiting for approval can be reviewed."))
        note = (note or "").strip()
        if decision == "reject" and not note:
            raise ValidationError(_("A rejection reason is required."))
        if decision not in ("approve", "reject"):
            raise ValidationError(_("The review decision is invalid."))
        approval_user = manager_employee.user_id or self.employee_id.leave_manager_id
        if not approval_user:
            raise ValidationError(_("The manager must be linked to an Odoo user before reviewing time off."))
        leave_as_manager = self.sudo().with_user(approval_user)
        if decision == "approve":
            leave_as_manager.action_approve()
            approver_field = "second_approver_id" if self.state == "validate" else "first_approver_id"
            values = {approver_field: manager_employee.id}
        else:
            leave_as_manager.action_refuse()
            values = {"first_approver_id": manager_employee.id}
        values.update({
            "mobile_review_note": note or False,
            "mobile_reviewed_by_employee_id": manager_employee.id,
            "mobile_reviewed_at": fields.Datetime.now(),
        })
        self.sudo().write(values)
        return True
