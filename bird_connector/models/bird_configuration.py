from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BirdConfiguration(models.Model):
    _name = "bird.configuration"
    _description = "Bird Connector Configuration"
    _order = "active desc, id desc"

    name = fields.Char(string="Configuration Name", required=True, default="Default Configuration")
    active = fields.Boolean(string="Active", default=True, help="Only the active configuration controls Bird background jobs and global connector defaults.")

    # Synchronization
    auto_sync_templates = fields.Boolean(
        string="Automatic Bird Sync",
        default=lambda self: self._param_bool("bird.auto_sync_templates", False),
        help="Periodically synchronize Bird connector data for active organizations.",
    )
    template_sync_interval = fields.Integer(
        string="Bird Sync Interval (Minutes)",
        default=lambda self: self._param_int("bird.template_sync_interval", 30),
    )
    auto_refresh_message_status = fields.Boolean(
        string="Automatic Message Status Refresh",
        default=lambda self: self._param_bool("bird.auto_refresh_message_status", True),
    )
    message_status_interval = fields.Integer(
        string="Message Status Interval (Minutes)",
        default=lambda self: self._param_int("bird.message_status_interval", 10),
    )

    # Wallet
    auto_refresh_balance = fields.Boolean(
        string="Automatic Wallet Balance Refresh",
        default=lambda self: self._param_bool("bird.auto_refresh_balance", False),
    )
    balance_refresh_interval = fields.Integer(
        string="Balance Refresh Interval (Minutes)",
        default=lambda self: self._param_int("bird.balance_refresh_interval", 60),
    )
    low_balance_notifications = fields.Boolean(
        string="Enable Low Balance Warnings",
        default=lambda self: self._param_bool("bird.low_balance_notifications", True),
        help="Use each Bird Organization's Low Balance Threshold when low-balance notifications are enabled.",
    )

    # Templates / technical
    default_locale = fields.Selection(
        [("en", "English"), ("ar", "Arabic")],
        string="Default Template Locale",
        default=lambda self: self.env["ir.config_parameter"].sudo().get_param("bird.default_locale", "en"),
        required=True,
    )
    request_timeout = fields.Integer(
        string="API Request Timeout (Seconds)",
        default=lambda self: self._param_int("bird.request_timeout", 20),
    )
    keep_api_responses = fields.Boolean(
        string="Keep API Responses for Debugging",
        default=lambda self: self._param_bool("bird.keep_api_responses", True),
    )

    @api.model
    def _param_bool(self, key, default=False):
        value = self.env["ir.config_parameter"].sudo().get_param(key)
        if value is None or value == "":
            return default
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    @api.model
    def _param_int(self, key, default):
        value = self.env["ir.config_parameter"].sudo().get_param(key)
        try:
            return max(int(value), 1) if value not in (None, "") else default
        except (TypeError, ValueError):
            return default

    @api.constrains("template_sync_interval", "message_status_interval", "balance_refresh_interval", "request_timeout")
    def _check_positive_intervals(self):
        for rec in self:
            if rec.template_sync_interval < 1:
                raise UserError(_("Bird Sync Interval must be at least 1 minute."))
            if rec.message_status_interval < 1:
                raise UserError(_("Message Status Interval must be at least 1 minute."))
            if rec.balance_refresh_interval < 1:
                raise UserError(_("Balance Refresh Interval must be at least 1 minute."))
            if rec.request_timeout < 1:
                raise UserError(_("API Request Timeout must be at least 1 second."))

    def _update_cron(self, xmlid, enabled, interval):
        cron = self.env.ref(xmlid, raise_if_not_found=False)
        if cron:
            cron.sudo().write({
                "active": bool(enabled),
                "interval_number": max(int(interval or 1), 1),
                "interval_type": "minutes",
            })

    def _apply_as_active_configuration(self):
        self.ensure_one()
        if not self.active:
            return

        # Keep only one configuration active. Old configurations remain available
        # in the list as history without affecting the connector.
        others = self.sudo().search([("id", "!=", self.id), ("active", "=", True)])
        if others:
            others.with_context(skip_bird_config_apply=True).write({"active": False})

        params = self.env["ir.config_parameter"].sudo()
        mapping = {
            "bird.auto_sync_templates": self.auto_sync_templates,
            "bird.template_sync_interval": self.template_sync_interval,
            "bird.auto_refresh_message_status": self.auto_refresh_message_status,
            "bird.message_status_interval": self.message_status_interval,
            "bird.auto_refresh_balance": self.auto_refresh_balance,
            "bird.balance_refresh_interval": self.balance_refresh_interval,
            "bird.low_balance_notifications": self.low_balance_notifications,
            "bird.default_locale": self.default_locale,
            "bird.request_timeout": self.request_timeout,
            "bird.keep_api_responses": self.keep_api_responses,
        }
        for key, value in mapping.items():
            params.set_param(key, value)

        self._update_cron(
            "bird_connector.ir_cron_bird_sync_connector",
            self.auto_sync_templates,
            self.template_sync_interval,
        )
        self._update_cron(
            "bird_connector.ir_cron_bird_refresh_message_status",
            self.auto_refresh_message_status,
            self.message_status_interval,
        )
        self._update_cron(
            "bird_connector.ir_cron_bird_refresh_balance",
            self.auto_refresh_balance,
            self.balance_refresh_interval,
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records.filtered("active"):
            rec._apply_as_active_configuration()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_bird_config_apply"):
            active_records = self.filtered("active")
            # The normal UI edits one record at a time. If a bulk write occurs,
            # applying the newest record keeps the result deterministic.
            if active_records:
                active_records.sorted("id")[-1]._apply_as_active_configuration()
        return res

    def action_activate_configuration(self):
        self.ensure_one()
        self.write({"active": True})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bird Configuration Activated"),
                "message": _("%s is now the active Bird Connector configuration.") % self.display_name,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def action_clean_duplicate_templates(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only administrators can run Bird template cleanup."))
        result = self.env["bird.template"].sudo()._cleanup_duplicate_projects()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bird Template Cleanup"),
                "message": _("Merged %(removed)s duplicate template record(s) across %(groups)s project group(s).") % {
                    "removed": result.get("removed", 0),
                    "groups": result.get("groups", 0),
                },
                "type": "success",
                "sticky": False,
            },
        }
