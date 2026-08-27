from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CpanelMailboxCreateWizard(models.TransientModel):
    _name = "cpanel.mailbox.create.wizard"
    _description = "Create cPanel Mailbox"

    server_id = fields.Many2one("cpanel.server", required=True)
    username = fields.Char(required=True)
    domain_id = fields.Many2one(
        "cpanel.domain",
        required=True,
        domain="[('server_id', '=', server_id), ('remote_exists', '=', True)]",
    )
    email_preview = fields.Char(string="Email Address", compute="_compute_email_preview")
    password = fields.Char(required=True)
    quota_mb = fields.Integer(default=1024, help="Use 0 for unlimited quota.")

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        if "server_id" in field_list and not values.get("server_id"):
            server = self.env["cpanel.server"].search([("active", "=", True)], limit=1)
            values["server_id"] = server.id
        if "domain_id" in field_list and values.get("server_id"):
            domain = self.env["cpanel.domain"].search(
                [("server_id", "=", values["server_id"]), ("remote_exists", "=", True)],
                order="domain_type, name",
                limit=1,
            )
            values["domain_id"] = domain.id
        return values

    @api.depends("username", "domain_id.name")
    def _compute_email_preview(self):
        for wizard in self:
            wizard.email_preview = (
                "%s@%s" % (wizard.username.strip(), wizard.domain_id.name)
                if wizard.username and wizard.domain_id
                else False
            )

    @api.onchange("server_id")
    def _onchange_server_id(self):
        if self.domain_id.server_id != self.server_id:
            self.domain_id = False
        if self.server_id and not self.domain_id:
            self.domain_id = self.env["cpanel.domain"].search(
                [("server_id", "=", self.server_id.id), ("remote_exists", "=", True)],
                order="domain_type, name",
                limit=1,
            )

    def action_create(self):
        self.ensure_one()
        if "@" in self.username or not self.username.strip():
            raise ValidationError(_("Enter only the part before @ as the username."))
        domain = self.domain_id.name
        self.server_id._api_call("Email", "add_pop", {"email": self.username.strip(), "domain": domain, "password": self.password, "quota": self.quota_mb})
        self.server_id._log("create", True, _("Created mailbox %s@%s") % (self.username, domain))
        self.server_id._sync_mailboxes()
        return {"type": "ir.actions.act_window_close"}


class CpanelMailboxPasswordWizard(models.TransientModel):
    _name = "cpanel.mailbox.password.wizard"
    _description = "Change cPanel Mailbox Password"

    mailbox_id = fields.Many2one("cpanel.mailbox", required=True)
    password = fields.Char(required=True)

    def action_apply(self):
        self.ensure_one()
        local, domain = self.mailbox_id.name.split("@", 1)
        self.mailbox_id._run("password", "passwd_pop", {"email": local, "domain": domain, "password": self.password})
        return {"type": "ir.actions.act_window_close"}


class CpanelMailboxQuotaWizard(models.TransientModel):
    _name = "cpanel.mailbox.quota.wizard"
    _description = "Change cPanel Mailbox Quota"

    mailbox_id = fields.Many2one("cpanel.mailbox", required=True)
    quota_mb = fields.Integer(required=True)

    def action_apply(self):
        self.ensure_one()
        local, domain = self.mailbox_id.name.split("@", 1)
        self.mailbox_id._run("quota", "edit_pop_quota", {"email": local, "domain": domain, "quota": self.quota_mb})
        return {"type": "ir.actions.act_window_close"}


class CpanelForwarderCreateWizard(models.TransientModel):
    _name = "cpanel.forwarder.create.wizard"
    _description = "Create cPanel Email Forwarder"

    server_id = fields.Many2one("cpanel.server", required=True)
    domain_id = fields.Many2one(
        "cpanel.domain",
        required=True,
        domain="[('server_id', '=', server_id), ('remote_exists', '=', True)]",
    )
    username = fields.Char(string="Address to Forward", required=True)
    source_preview = fields.Char(string="Email Address", compute="_compute_source_preview")
    destination_type = fields.Selection(
        [("fwd", "Forward to Email Address"), ("fail", "Discard and Send an Error")],
        default="fwd",
        required=True,
    )
    destination = fields.Char(string="Forward To")
    failure_message = fields.Char(default="No such person at this address.")

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        if "server_id" in field_list and not values.get("server_id"):
            server = self.env["cpanel.server"].search([("active", "=", True)], limit=1)
            values["server_id"] = server.id
        if "domain_id" in field_list and values.get("server_id"):
            domain = self.env["cpanel.domain"].search(
                [("server_id", "=", values["server_id"]), ("remote_exists", "=", True)],
                order="domain_type, name",
                limit=1,
            )
            values["domain_id"] = domain.id
        return values

    @api.depends("username", "domain_id.name")
    def _compute_source_preview(self):
        for wizard in self:
            wizard.source_preview = (
                "%s@%s" % (wizard.username.strip(), wizard.domain_id.name)
                if wizard.username and wizard.domain_id
                else False
            )

    @api.onchange("server_id")
    def _onchange_server_id(self):
        if self.domain_id.server_id != self.server_id:
            self.domain_id = False
        if self.server_id and not self.domain_id:
            self.domain_id = self.env["cpanel.domain"].search(
                [("server_id", "=", self.server_id.id), ("remote_exists", "=", True)],
                order="domain_type, name",
                limit=1,
            )

    def action_create(self):
        self.ensure_one()
        if "@" in self.username or not self.username.strip():
            raise ValidationError(_("Enter only the part before @ as the address."))
        params = {
            "domain": self.domain_id.name,
            "email": self.source_preview,
            "fwdopt": self.destination_type,
        }
        if self.destination_type == "fwd":
            if not self.destination or "@" not in self.destination:
                raise ValidationError(_("Enter a valid destination email address."))
            params["fwdemail"] = self.destination.strip()
        else:
            params["failmsgs"] = self.failure_message or "No such person at this address."
        self.server_id._api_call("Email", "add_forwarder", params)
        self.server_id._log("create_forwarder", True, _("Created forwarder for %s") % self.source_preview)
        self.server_id._sync_forwarders()
        return {"type": "ir.actions.act_window_close"}
