from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FastFinancialRebuildWizard(models.TransientModel):
    _name = "fast.financial.rebuild.wizard"
    _description = "Queue Fast Financial Reporting Rebuild"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
    )
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    confirmation = fields.Boolean(
        string="I understand this will read posted journal items for the selected period",
        default=False,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise UserError(_("Start Date must be before or equal to End Date."))

    def action_queue_rebuild(self):
        self.ensure_one()
        if not self.confirmation:
            raise UserError(_("Please confirm the rebuild before queuing it."))

        existing = self.env["fast.financial.rebuild.job"].search([
            ("company_id", "=", self.company_id.id),
            ("state", "in", ("queued", "running")),
        ], limit=1)
        if existing:
            raise UserError(_("There is already a queued or running rebuild job."))

        total_days = (self.date_to - self.date_from).days + 1
        job = self.env["fast.financial.rebuild.job"].create({
            "name": _("Rebuild %s to %s") % (self.date_from, self.date_to),
            "company_id": self.company_id.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "next_date": self.date_from,
            "total_days": total_days,
        })

        self.env["fast.financial.sync.state"].sudo().get_or_create_for_company(self.company_id)

        return {
            "type": "ir.actions.act_window",
            "name": _("Rebuild Job"),
            "res_model": "fast.financial.rebuild.job",
            "res_id": job.id,
            "view_mode": "form",
            "target": "current",
        }
