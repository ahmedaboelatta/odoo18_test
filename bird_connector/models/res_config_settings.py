from odoo import api, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Legacy/global fallback credentials. Organization records remain the source
    # of truth for real connector credentials; these are kept for compatibility.
    bird_access_key = fields.Char(
        string="Bird Access Key (Legacy Fallback)",
        config_parameter="bird.access_key",
    )
    bird_workspace_id = fields.Char(
        string="Bird Workspace ID (Legacy Fallback)",
        config_parameter="bird.workspace_id",
    )

    # Synchronization
    bird_auto_sync_templates = fields.Boolean(
        string="Automatic Bird Sync",
        config_parameter="bird.auto_sync_templates",
        default=False,
        help="Periodically synchronize workspaces, channels and templates for active Bird organizations.",
    )
    bird_template_sync_interval = fields.Integer(
        string="Bird Sync Interval (Minutes)",
        config_parameter="bird.template_sync_interval",
        default=30,
    )
    bird_auto_refresh_message_status = fields.Boolean(
        string="Automatic Message Status Refresh",
        config_parameter="bird.auto_refresh_message_status",
        default=True,
    )
    bird_message_status_interval = fields.Integer(
        string="Message Status Interval (Minutes)",
        config_parameter="bird.message_status_interval",
        default=10,
    )

    # Wallet
    bird_auto_refresh_balance = fields.Boolean(
        string="Automatic Wallet Balance Refresh",
        config_parameter="bird.auto_refresh_balance",
        default=False,
    )
    bird_balance_refresh_interval = fields.Integer(
        string="Balance Refresh Interval (Minutes)",
        config_parameter="bird.balance_refresh_interval",
        default=60,
    )
    bird_low_balance_notifications = fields.Boolean(
        string="Enable Low Balance Warnings",
        config_parameter="bird.low_balance_notifications",
        default=True,
        help="Allows the connector to flag low balances using each Organization's Low Balance Threshold.",
    )

    # Template defaults / technical behavior
    bird_default_locale = fields.Selection(
        [("en", "English"), ("ar", "Arabic")],
        string="Default Template Locale",
        config_parameter="bird.default_locale",
        default="en",
    )
    bird_request_timeout = fields.Integer(
        string="API Request Timeout (Seconds)",
        config_parameter="bird.request_timeout",
        default=20,
    )
    bird_keep_api_responses = fields.Boolean(
        string="Keep API Responses for Debugging",
        config_parameter="bird.keep_api_responses",
        default=True,
    )

    def _update_cron(self, xmlid, active, interval):
        cron = self.env.ref(xmlid, raise_if_not_found=False)
        if not cron:
            return
        interval = max(int(interval or 1), 1)
        cron.sudo().write({
            "active": bool(active),
            "interval_number": interval,
            "interval_type": "minutes",
        })

    def set_values(self):
        res = super().set_values()
        self.ensure_one()
        self._update_cron(
            "bird_connector.ir_cron_bird_sync_connector",
            self.bird_auto_sync_templates,
            self.bird_template_sync_interval,
        )
        self._update_cron(
            "bird_connector.ir_cron_bird_refresh_message_status",
            self.bird_auto_refresh_message_status,
            self.bird_message_status_interval,
        )
        self._update_cron(
            "bird_connector.ir_cron_bird_refresh_balance",
            self.bird_auto_refresh_balance,
            self.bird_balance_refresh_interval,
        )
        return res

    def action_bird_cleanup_duplicate_templates(self):
        """Manual, admin-only cleanup for historical version duplicates."""
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise UserError("Only administrators can run Bird template cleanup.")
        result = self.env["bird.template"].sudo()._cleanup_duplicate_projects()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Bird Template Cleanup",
                "message": "Merged %s duplicate template record(s) across %s project group(s)." % (
                    result.get("removed", 0), result.get("groups", 0)
                ),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
