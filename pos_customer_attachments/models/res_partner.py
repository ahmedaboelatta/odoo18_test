
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    pos_attachment_required = fields.Boolean(
        string="Require POS Order Attachments",
        help=(
            "When enabled, new POS orders created for this customer are marked "
            "as requiring supporting attachments."
        ),
    )
    pos_minimum_attachments = fields.Integer(
        string="Minimum Required Attachments",
        default=1,
        help="Minimum number of attachments expected on each applicable POS order.",
    )
    pos_auto_rename_attachments = fields.Boolean(
        string="Auto-Rename Uploaded POS Images",
        default=True,
        help=(
            "When enabled, images uploaded from the POS order Upload File button "
            "are renamed using the order reference and date."
        ),
    )

    def _can_manage_pos_attachment_policy(self):
        return (
            self.env.is_superuser()
            or self.env.user.has_group(
                "pos_customer_attachments.group_pos_attachment_policy_manager"
            )
            or self.env.user.has_group("base.group_system")
        )

    @api.model
    def _check_pos_attachment_policy_access(self, vals):
        protected_fields = {
            "pos_attachment_required",
            "pos_minimum_attachments",
            "pos_auto_rename_attachments",
        }

        if protected_fields.intersection(vals) and not self._can_manage_pos_attachment_policy():
            raise AccessError(
                _(
                    "You are not allowed to change the POS Attachment Policy. "
                    "Please contact a user with the 'Manage Customer Attachment Policy' access right."
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        # Only block explicit attempts to configure the policy.
        # Normal customer creation remains governed by Odoo's standard Contact permissions.
        for vals in vals_list:
            explicitly_configured = (
                vals.get("pos_attachment_required")
                or (
                    "pos_minimum_attachments" in vals
                    and vals.get("pos_minimum_attachments") not in (False, 0, 1)
                )
                or (
                    "pos_auto_rename_attachments" in vals
                    and vals.get("pos_auto_rename_attachments") is False
                )
            )
            if explicitly_configured:
                self._check_pos_attachment_policy_access(vals)

        return super().create(vals_list)

    def write(self, vals):
        protected_fields = {
            "pos_attachment_required",
            "pos_minimum_attachments",
            "pos_auto_rename_attachments",
        }

        if protected_fields.intersection(vals):
            self._check_pos_attachment_policy_access(vals)

        return super().write(vals)

    @api.constrains("pos_minimum_attachments")
    def _check_pos_minimum_attachments(self):
        for partner in self:
            if partner.pos_minimum_attachments < 1:
                raise ValidationError(
                    _("Minimum Required Attachments must be at least 1.")
                )
