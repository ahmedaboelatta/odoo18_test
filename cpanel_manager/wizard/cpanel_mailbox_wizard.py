from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CpanelMailboxCreateWizard(models.TransientModel):
    _name = "cpanel.mailbox.create.wizard"
    _description = "Create cPanel Mailbox"

    server_id = fields.Many2one("cpanel.server", required=True)
    template_id = fields.Many2one("cpanel.mailbox.template", string="Mailbox Template")
    username = fields.Char(required=True)
    domain_id = fields.Many2one(
        "cpanel.domain",
        required=True,
        domain="[('server_id', '=', server_id), ('remote_exists', '=', True)]",
    )
    email_preview = fields.Char(string="Email Address", compute="_compute_email_preview")
    password = fields.Char(required=True)
    quota_mb = fields.Integer(default=1024, help="Use 0 for unlimited quota.")
    tag_ids = fields.Many2many("cpanel.mailbox.tag", string="Tags")

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

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if self.template_id:
            self.quota_mb = self.template_id.quota_mb
            self.tag_ids = self.template_id.tag_ids

    def action_create(self):
        self.ensure_one()
        if "@" in self.username or not self.username.strip():
            raise ValidationError(_("Enter only the part before @ as the username."))
        domain = self.domain_id.name
        self.server_id._api_call("Email", "add_pop", {"email": self.username.strip(), "domain": domain, "password": self.password, "quota": self.quota_mb})
        self.server_id._log("create", True, _("Created mailbox %s@%s") % (self.username, domain))
        self.server_id._sync_mailboxes()
        mailbox = self.env["cpanel.mailbox"].search([
            ("server_id", "=", self.server_id.id),
            ("name", "=", "%s@%s" % (self.username.strip().lower(), domain.lower())),
        ], limit=1)
        if mailbox and self.tag_ids:
            mailbox.tag_ids = self.tag_ids
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

    forwarder_id = fields.Many2one("cpanel.forwarder", readonly=True)
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
        forwarder = self.env["cpanel.forwarder"].browse(
            self.env.context.get("default_forwarder_id")
        ).exists()
        if forwarder:
            local, domain_name = forwarder.source.split("@", 1)
            domain = self.env["cpanel.domain"].search([
                ("server_id", "=", forwarder.server_id.id),
                ("name", "=", domain_name),
            ], limit=1)
            values.update({
                "forwarder_id": forwarder.id,
                "server_id": forwarder.server_id.id,
                "domain_id": domain.id,
                "username": local,
                "destination_type": "fwd",
                "destination": forwarder.destination,
            })
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
            destination = self.destination.strip().lower()
            destination_domain = destination.rsplit("@", 1)[1]
            local_domain = self.env["cpanel.domain"].search_count([
                ("server_id", "=", self.server_id.id),
                ("name", "=", destination_domain),
                ("remote_exists", "=", True),
            ])
            if local_domain:
                mailbox_exists = self.env["cpanel.mailbox"].search_count([
                    ("server_id", "=", self.server_id.id),
                    ("name", "=", destination),
                    ("remote_exists", "=", True),
                ])
                alias_exists = self.env["cpanel.forwarder"].search_count([
                    ("server_id", "=", self.server_id.id),
                    ("source", "=", destination),
                    ("remote_exists", "=", True),
                ])
                if not mailbox_exists and not alias_exists:
                    raise ValidationError(_(
                        "The local destination %s does not exist in this cPanel account. "
                        "Create that mailbox first, select an existing local mailbox, or use an external email address."
                    ) % destination)
            params["fwdemail"] = destination
        else:
            params["failmsgs"] = self.failure_message or "No such person at this address."
        unchanged = bool(
            self.forwarder_id
            and self.destination_type == "fwd"
            and self.forwarder_id.source == self.source_preview.lower()
            and self.forwarder_id.destination == self.destination.strip().lower()
        )
        if unchanged:
            return {"type": "ir.actions.act_window_close"}
        self.server_id._api_call("Email", "add_forwarder", params)
        if self.forwarder_id and (
            self.forwarder_id.source != self.source_preview.lower()
            or self.forwarder_id.destination != (self.destination or "").strip().lower()
        ):
            self.server_id._api_call(
                "Email",
                "delete_forwarder",
                {
                    "email": self.forwarder_id.source,
                    "emaildest": self.forwarder_id.destination,
                },
            )
        self.server_id._log("create_forwarder", True, _("Created forwarder for %s") % self.source_preview)
        self.server_id._sync_forwarders()
        return {"type": "ir.actions.act_window_close"}


class CpanelMailboxBulkWizard(models.TransientModel):
    _name = "cpanel.mailbox.bulk.wizard"
    _description = "Bulk cPanel Mailbox Operation"

    mailbox_ids = fields.Many2many("cpanel.mailbox", required=True)
    operation = fields.Selection(
        [
            ("add_tags", "Add Tags"),
            ("remove_tags", "Remove Tags"),
            ("quota", "Change Quota"),
            ("suspend", "Suspend Completely"),
            ("restore", "Restore"),
        ],
        required=True,
        default="add_tags",
    )
    tag_ids = fields.Many2many("cpanel.mailbox.tag", string="Tags")
    quota_mb = fields.Integer(string="Quota (MB)", default=1024)

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        if "mailbox_ids" in field_list and self.env.context.get("active_model") == "cpanel.mailbox":
            values["mailbox_ids"] = [(6, 0, self.env.context.get("active_ids", []))]
        return values

    def action_apply(self):
        self.ensure_one()
        if not self.mailbox_ids:
            raise ValidationError(_("Select at least one mailbox."))
        if self.operation in ("add_tags", "remove_tags"):
            if not self.tag_ids:
                raise ValidationError(_("Select at least one tag."))
            command = 4 if self.operation == "add_tags" else 3
            for mailbox in self.mailbox_ids:
                mailbox.write({"tag_ids": [(command, tag.id) for tag in self.tag_ids]})
            return {"type": "ir.actions.act_window_close"}

        servers = self.mailbox_ids.mapped("server_id")
        for mailbox in self.mailbox_ids.filtered("remote_exists"):
            if self.operation == "quota":
                local, domain = mailbox.name.split("@", 1)
                mailbox.server_id._api_call(
                    "Email", "edit_pop_quota",
                    {"email": local, "domain": domain, "quota": self.quota_mb},
                )
            else:
                functions = (
                    ("suspend_login", "suspend_incoming", "suspend_outgoing")
                    if self.operation == "suspend"
                    else ("unsuspend_login", "unsuspend_incoming", "unsuspend_outgoing")
                )
                for function in functions:
                    mailbox.server_id._api_call("Email", function, {"email": mailbox.name})
            mailbox.server_id._log(
                "bulk_%s" % self.operation,
                True,
                _("Bulk operation completed for %s") % mailbox.name,
                mailbox,
            )
        for server in servers:
            server._sync_mailboxes()
        return {"type": "ir.actions.act_window_close"}
