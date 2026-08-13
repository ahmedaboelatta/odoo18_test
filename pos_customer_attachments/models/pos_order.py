from collections import Counter

from odoo import api, fields, models, _
from odoo.tools import SQL


class PosOrder(models.Model):
    _inherit = "pos.order"

    attachment_required = fields.Boolean(
        string="Attachment Required",
        readonly=True,
        copy=False,
        index=True,
        help=(
            "Snapshot of the customer's POS attachment policy when this order "
            "was created."
        ),
    )
    minimum_required_attachments = fields.Integer(
        string="Minimum Required Attachments",
        readonly=True,
        copy=False,
        default=0,
        help=(
            "Snapshot of the minimum required attachment count when this order "
            "was created."
        ),
    )
    auto_rename_pos_attachments = fields.Boolean(
        string="Auto-Rename POS Images",
        readonly=True,
        copy=False,
        default=True,
        help=(
            "Snapshot of the customer's image auto-rename preference when this "
            "order was created."
        ),
    )

    attachment_count = fields.Integer(
        string="Attachments",
        compute="_compute_attachment_metrics",
        compute_sudo=True,
    )
    has_attachment = fields.Boolean(
        string="Has Attachments",
        compute="_compute_attachment_metrics",
        compute_sudo=True,
        search="_search_has_attachment",
    )
    attachment_missing = fields.Boolean(
        string="Missing Required Attachments",
        compute="_compute_attachment_metrics",
        compute_sudo=True,
        search="_search_attachment_missing",
    )
    attachment_status = fields.Selection(
        selection=[
            ("not_required", "Not Required"),
            ("missing", "Missing"),
            ("partial", "Partial"),
            ("complete", "Complete"),
        ],
        string="Attachment Status",
        compute="_compute_attachment_metrics",
        compute_sudo=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        Partner = self.env["res.partner"]
        for vals in vals_list:
            partner_id = vals.get("partner_id")
            if partner_id:
                partner = Partner.browse(partner_id)
                required = bool(partner.pos_attachment_required)
                vals.setdefault("attachment_required", required)
                vals.setdefault(
                    "minimum_required_attachments",
                    partner.pos_minimum_attachments if required else 0,
                )
                vals.setdefault(
                    "auto_rename_pos_attachments",
                    bool(partner.pos_auto_rename_attachments),
                )
            else:
                vals.setdefault("attachment_required", False)
                vals.setdefault("minimum_required_attachments", 0)
        return super().create(vals_list)

    def _compute_attachment_metrics(self):
        counts = Counter()
        order_ids = self.ids
        if order_ids:
            attachments = self.env["ir.attachment"].sudo().search([
                ("res_model", "=", "pos.order"),
                ("res_id", "in", order_ids),
            ])
            counts.update(attachments.mapped("res_id"))

        for order in self:
            count = counts.get(order.id, 0)
            minimum = max(order.minimum_required_attachments or 0, 1)
            required = bool(order.attachment_required)

            order.attachment_count = count
            order.has_attachment = count > 0
            order.attachment_missing = required and count < minimum

            if not required:
                order.attachment_status = "not_required"
            elif count == 0:
                order.attachment_status = "missing"
            elif count < minimum:
                order.attachment_status = "partial"
            else:
                order.attachment_status = "complete"

    @api.model
    def _search_has_attachment(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise NotImplementedError(
                _("Has Attachments only supports boolean equality searches.")
            )

        wants_attachments = value if operator == "=" else not value
        sql = SQL(
            """
            SELECT DISTINCT ia.res_id
              FROM ir_attachment ia
             WHERE ia.res_model = 'pos.order'
               AND ia.res_id IS NOT NULL
            """
        )
        return [("id", "in" if wants_attachments else "not in", sql)]

    @api.model
    def _search_attachment_missing(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise NotImplementedError(
                _("Missing Required Attachments only supports boolean equality searches.")
            )

        wants_missing = value if operator == "=" else not value
        sql = SQL(
            """
            SELECT po.id
              FROM pos_order po
             WHERE po.attachment_required IS TRUE
               AND (
                    SELECT COUNT(*)
                      FROM ir_attachment ia
                     WHERE ia.res_model = 'pos.order'
                       AND ia.res_id = po.id
                   ) < GREATEST(po.minimum_required_attachments, 1)
            """
        )
        return [("id", "in" if wants_missing else "not in", sql)]

    def action_upload_pos_attachment(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Upload POS Attachment"),
            "res_model": "pos.order.attachment.upload.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
            },
        }
