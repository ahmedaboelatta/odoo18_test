from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CpanelMailbox(models.Model):
    _name = "cpanel.mailbox"
    _description = "cPanel Mailbox"
    _order = "name"

    name = fields.Char(string="Email Address", required=True, index=True)
    employee_id = fields.Many2one(
        "hr.employee.public",
        string="Employee",
        ondelete="set null",
        index=True,
        domain="[('company_id', '=', company_id)]",
        help="Employee who owns or uses this mailbox.",
    )
    server_id = fields.Many2one("cpanel.server", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="server_id.company_id", store=True, index=True)
    domain = fields.Char(required=True, index=True)
    # MB avoids PostgreSQL int4 overflow and is easier to read in the UI.
    # New names also make upgrades safe if legacy byte columns remain integer.
    used_mb = fields.Float(string="Used (MB)", readonly=True, digits=(16, 2))
    used_gb = fields.Float(string="Used (GB)", compute="_compute_usage", digits=(16, 3))
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
            record.used_gb = record.used_mb / 1024.0
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

    def _set_restriction(self, restriction, suspended):
        functions = {
            "login": ("suspend_login", "unsuspend_login"),
            "incoming": ("suspend_incoming", "unsuspend_incoming"),
            "outgoing": ("suspend_outgoing", "unsuspend_outgoing"),
        }
        if restriction not in functions:
            raise UserError(_("Unsupported mailbox restriction."))
        function = functions[restriction][0 if suspended else 1]
        operation = "suspend_%s" % restriction if suspended else "allow_%s" % restriction
        for record in self:
            if restriction == "login":
                record._set_login_restriction(function, operation, suspended)
            else:
                record._run(operation, function)
        return True

    def _get_remote_login_suspension(self):
        """Read the effective login state instead of trusting UAPI status=1."""
        self.ensure_one()
        rows = self.server_id._api_call(
            "Email", "list_pops_with_disk", {"get_restrictions": 1, "skip_main": 0}
        ) or []
        if isinstance(rows, dict):
            rows = rows.get("pops") or rows.get("data") or []
        wanted = (self.name or "").strip().lower()
        for row in rows:
            address = (row.get("email") or row.get("login") or "").strip().lower()
            if address == wanted:
                value = row.get("suspended_login")
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes", "suspended")
                return bool(value)
        return None

    def _set_login_restriction(self, function, operation, suspended):
        """Apply the documented full-address call and verify its remote result."""
        self.ensure_one()
        try:
            self.server_id._api_call("Email", function, {"email": self.name})
            actual = self._get_remote_login_suspension()

            self.server_id._sync_mailboxes()
            if actual is not suspended:
                action = _("suspend") if suspended else _("allow")
                raise UserError(
                    _(
                        "cPanel accepted the request but did not %(action)s login for "
                        "%(email)s. No local status was changed. Please check the "
                        "mailbox Login restriction in cPanel or the server API permissions."
                    )
                    % {"action": action, "email": self.name}
                )
            self.server_id._log(
                operation, True, _("Operation completed and verified for %s") % self.name, self
            )
        except UserError as exc:
            self.server_id._log(operation, False, str(exc), self)
            raise
        return True

    def action_suspend_login(self):
        return self._set_restriction("login", True)

    def action_allow_login(self):
        return self._set_restriction("login", False)

    def action_suspend_incoming(self):
        return self._set_restriction("incoming", True)

    def action_allow_incoming(self):
        return self._set_restriction("incoming", False)

    def action_suspend_outgoing(self):
        return self._set_restriction("outgoing", True)

    def action_allow_outgoing(self):
        return self._set_restriction("outgoing", False)

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
