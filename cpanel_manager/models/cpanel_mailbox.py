from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CpanelMailbox(models.Model):
    _name = "cpanel.mailbox"
    _description = "cPanel Mailbox"
    _order = "name"

    name = fields.Char(string="Email Address", required=True, index=True)
    server_id = fields.Many2one("cpanel.server", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="server_id.company_id", store=True, index=True)
    domain = fields.Char(required=True, index=True)
    # MB avoids PostgreSQL int4 overflow and is easier to read in the UI.
    # New names also make upgrades safe if legacy byte columns remain integer.
    used_mb = fields.Float(string="Used (MB)", readonly=True, digits=(16, 2))
    quota_mb = fields.Float(string="Quota (MB)", readonly=True, digits=(16, 2))
    quota_display = fields.Char(string="Quota (MB)", compute="_compute_quota_status")
    quota_gb_display = fields.Char(string="Quota (GB)", compute="_compute_quota_status")
    usage_percent = fields.Float(compute="_compute_usage")
    suspended_login = fields.Boolean(readonly=True)
    suspended_incoming = fields.Boolean(readonly=True)
    suspended_outgoing = fields.Boolean(readonly=True)
    is_restricted = fields.Boolean(compute="_compute_quota_status", store=True, index=True)
    is_unlimited = fields.Boolean(compute="_compute_quota_status", store=True, index=True)
    is_over_quota = fields.Boolean(compute="_compute_quota_status", store=True, index=True)
    is_system_account = fields.Boolean(readonly=True, index=True)
    tag_ids = fields.Many2many(
        "cpanel.mailbox.tag",
        "cpanel_mailbox_tag_rel",
        "mailbox_id",
        "tag_id",
        string="Tags",
    )
    remote_exists = fields.Boolean(default=True, readonly=True)
    last_sync = fields.Datetime(readonly=True)

    _sql_constraints = [("server_email_unique", "unique(server_id, name)", "This mailbox already exists on this server.")]

    @api.depends("used_mb", "quota_mb")
    def _compute_usage(self):
        for record in self:
            record.usage_percent = record.quota_mb and (100.0 * record.used_mb / record.quota_mb) or 0.0

    @api.depends(
        "quota_mb",
        "used_mb",
        "suspended_login",
        "suspended_incoming",
        "suspended_outgoing",
    )
    def _compute_quota_status(self):
        for record in self:
            record.is_unlimited = not record.quota_mb
            record.is_over_quota = bool(record.quota_mb and record.used_mb > record.quota_mb)
            record.is_restricted = bool(
                record.suspended_login
                or record.suspended_incoming
                or record.suspended_outgoing
            )
            if not record.quota_mb:
                record.quota_display = _("Unlimited")
                record.quota_gb_display = _("Unlimited")
            else:
                record.quota_display = _("%.2f MB") % record.quota_mb
                record.quota_gb_display = _("%.2f GB") % (record.quota_mb / 1024.0)

    def _run(self, operation, function, params=None):
        self.ensure_one()
        try:
            self.server_id._api_call("Email", function, params or {"email": self.name})
            self.server_id._log(operation, True, _("Operation completed for %s") % self.name, self)
            self.server_id._sync_mailboxes()
        except UserError as exc:
            self.server_id._log(operation, False, str(exc), self)
            raise
        return True

    def action_suspend(self):
        for record in self:
            for operation in ("suspend_login", "suspend_incoming", "suspend_outgoing"):
                record._run("suspend", operation)
        return True

    def action_unsuspend(self):
        for record in self:
            for operation in ("unsuspend_login", "unsuspend_incoming", "unsuspend_outgoing"):
                record._run("unsuspend", operation)
        return True

    def action_delete_remote(self):
        for record in self:
            record._run("delete", "delete_pop", {"email": record.name})
        return True

    def action_change_password(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Change Mailbox Password"), "res_model": "cpanel.mailbox.password.wizard", "view_mode": "form", "target": "new", "context": {"default_mailbox_id": self.id}}

    def action_change_quota(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Change Mailbox Quota"), "res_model": "cpanel.mailbox.quota.wizard", "view_mode": "form", "target": "new", "context": {"default_mailbox_id": self.id, "default_quota_mb": int(self.quota_mb) if self.quota_mb else 0}}

    def action_open_webmail(self):
        self.ensure_one()
        if not self.remote_exists:
            raise UserError(_("This mailbox no longer exists in cPanel."))
        return {
            "type": "ir.actions.act_url",
            "url": "/cpanel/webmail/%s" % self.id,
            "target": "new",
        }
