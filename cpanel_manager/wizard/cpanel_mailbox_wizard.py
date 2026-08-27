from odoo import _, fields, models
from odoo.exceptions import ValidationError


class CpanelMailboxCreateWizard(models.TransientModel):
    _name = "cpanel.mailbox.create.wizard"
    _description = "Create cPanel Mailbox"

    server_id = fields.Many2one("cpanel.server", required=True)
    username = fields.Char(required=True)
    domain = fields.Char(required=True)
    password = fields.Char(required=True)
    quota_mb = fields.Integer(default=1024, help="Use 0 for unlimited quota.")

    def action_create(self):
        self.ensure_one()
        if "@" in self.username or not self.username.strip():
            raise ValidationError(_("Enter only the part before @ as the username."))
        self.server_id._api_call("Email", "add_pop", {"email": self.username.strip(), "domain": self.domain.strip(), "password": self.password, "quota": self.quota_mb})
        self.server_id._log("create", True, _("Created mailbox %s@%s") % (self.username, self.domain))
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
