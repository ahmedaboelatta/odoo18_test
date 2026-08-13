from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
            "When enabled, images uploaded from the POS order Attachments button "
            "are renamed using the order reference, date, and attachment ID."
        ),
    )

    @api.constrains("pos_minimum_attachments")
    def _check_pos_minimum_attachments(self):
        for partner in self:
            if partner.pos_minimum_attachments < 1:
                raise ValidationError(
                    _("Minimum Required Attachments must be at least 1.")
                )
