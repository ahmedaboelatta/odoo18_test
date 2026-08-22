import requests
import json
import logging
import base64
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from odoo import models, fields, api, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class BirdOrganization(models.Model):
    _name = 'bird.organization'
    _description = 'Bird Organization'

    name = fields.Char(string='Organization Name', required=True)
    bird_id = fields.Char(string='Organization ID', help='Bird Organization UUID from Settings > Organization > Company profile.')
    access_key = fields.Char(string='Workspace Access Key', required=True, help='Bird Workspace Access Key used for workspaces, channels, templates and messages.')
    wallet_api_key = fields.Char(string='Wallet API Key', help='Organization-level Bird API key used only for Wallet/Reporting API requests. Keep separate from the Workspace Access Key when Bird requires organization-level financial permissions.')
    wallet_id = fields.Char(
        string='Wallet ID',
        help='Bird Wallet UUID from Settings > Billing > Plan & payment > Wallet. If empty, Refresh Balance will select the main wallet automatically.',
    )
    wallet_name = fields.Char(string='Wallet Name', readonly=True)
    wallet_usage_raw = fields.Text(string='Wallet API Response', readonly=True)
    balance_source = fields.Selection([
        ('bird_wallet', 'Bird Wallet API'),
        ('bird_reporting', 'Bird Reporting API (Legacy Connector Logic)'),
        ('manual', 'Manual'),
    ], string='Balance Source', readonly=True)
    workspace_id = fields.Char(string='Default Workspace ID', required=True, help='Primary Bird Workspace UUID used by this connector.')
    wallet_balance = fields.Float(string='Wallet Balance', digits=(16, 2))
    currency_code = fields.Char(string='Currency Code', default='EUR')
    low_balance_threshold = fields.Float(string='Low Balance Threshold', default=5.0)
    last_balance_sync = fields.Datetime(string='Last Balance Sync', readonly=True)
    state = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ], string='Status', default='active')


    # Organization-level connector configuration
    auto_sync_templates = fields.Boolean(
        string="Automatic Bird Sync", default=False,
        help="Automatically synchronize this organization's workspaces, channels and templates."
    )
    template_sync_interval = fields.Integer(
        string="Bird Sync Interval (Minutes)", default=30,
        help="Minimum number of minutes between automatic connector synchronizations."
    )
    last_auto_sync = fields.Datetime(string="Last Automatic Sync", readonly=True)

    auto_refresh_message_status = fields.Boolean(
        string="Automatic Message Status Refresh", default=True,
        help="Automatically refresh queued/sent message delivery status for this organization."
    )
    message_status_interval = fields.Integer(
        string="Message Status Interval (Minutes)", default=10,
        help="Minimum number of minutes between automatic message-status refresh cycles."
    )
    last_message_status_refresh = fields.Datetime(string="Last Message Status Refresh", readonly=True)

    auto_refresh_balance = fields.Boolean(
        string="Automatic Wallet Balance Refresh", default=False,
        help="Automatically refresh this organization's Bird wallet balance."
    )
    balance_refresh_interval = fields.Integer(
        string="Balance Refresh Interval (Minutes)", default=60,
        help="Minimum number of minutes between automatic wallet balance refreshes."
    )
    last_auto_balance_refresh = fields.Datetime(string="Last Automatic Balance Refresh", readonly=True)

    low_balance_notifications = fields.Boolean(
        string="Enable Low Balance Warning", default=True,
        help="Show a warning on this organization when the wallet balance is below the configured threshold."
    )
    default_locale = fields.Selection(
        [("en", "English"), ("ar", "Arabic")],
        string="Default Template Locale", default="en", required=True,
        help="Default locale for new templates linked to this organization."
    )
    default_country_id = fields.Many2one(
        'res.country',
        string='Default Contact Country',
        default=lambda self: self.env.ref('base.sa', raise_if_not_found=False),
        help=(
            'Country used to normalize manually entered local WhatsApp numbers. '
            'For example, with Saudi Arabia selected, 0501234567 is stored as +966501234567.'
        ),
    )
    request_timeout = fields.Integer(
        string="API Request Timeout (Seconds)", default=20,
        help="Default timeout used by organization-level Bird API calls."
    )
    keep_api_responses = fields.Boolean(
        string="Keep API Responses for Debugging", default=True,
        help="Keep raw Bird API responses in technical fields to simplify troubleshooting."
    )
    low_balance_warning = fields.Boolean(
        string="Low Balance", compute="_compute_low_balance_warning"
    )
    legacy_configuration_migrated = fields.Boolean(default=False, copy=False)
    

    # Real-time Bird webhook configuration
    webhook_token = fields.Char(string="Webhook Token", copy=False, readonly=True)
    webhook_signing_key = fields.Char(string="Webhook Signing Key", copy=False)
    webhook_verify_signatures = fields.Boolean(string="Verify Webhook Signatures", default=True)
    webhook_base_url = fields.Char(
        string="Webhook Base URL",
        help="Optional public HTTPS base URL for this Odoo server, for example https://odoo.example.com. "
             "If empty, Odoo uses the web.base.url system parameter.",
    )
    webhook_public_url = fields.Char(string="Webhook Public URL", compute="_compute_webhook_public_url")
    webhook_https_ready = fields.Boolean(string="HTTPS Ready", compute="_compute_webhook_public_url")
    webhook_subscription_ids = fields.One2many("bird.webhook.subscription", "organization_id", string="Webhooks")
    webhook_event_ids = fields.One2many("bird.webhook.event", "organization_id", string="Webhook Events")
    webhook_subscription_count = fields.Integer(compute="_compute_webhook_counts")
    webhook_event_count = fields.Integer(compute="_compute_webhook_counts")

    # Deployment diagnostics for webhook portability between Odoo servers.
    webhook_deployment_mode = fields.Selection([
        ("auto", "Auto Detect"),
        ("single_db", "Single Database / dbfilter"),
        ("dedicated", "Multi Database - Dedicated Webhook Instance"),
        ("external_proxy", "Multi Database - External / Proxy Routing"),
    ], string="Webhook Deployment Mode", default="auto", required=True,
       help=(
           "Controls how deployment readiness is evaluated. Auto Detect accepts either an explicit "
           "db_name/dbfilter match or a successfully received webhook as proof of routing. Dedicated "
           "Webhook Instance is intended for multi-database servers where normal Odoo traffic and Bird "
           "webhook traffic are routed to different Odoo workers/ports. External / Proxy Routing is for "
           "deployments where Nginx, a load balancer, gateway, or another router selects the target database."
       ))
    deployment_db_name = fields.Char(string="Current Database", compute="_compute_deployment_status")
    deployment_route_source = fields.Char(string="Routing Evidence", compute="_compute_deployment_status")
    deployment_dbfilter = fields.Char(string="DB Filter", compute="_compute_deployment_status")
    deployment_db_routing_ready = fields.Boolean(string="Database Routing Ready", compute="_compute_deployment_status")
    deployment_proxy_mode = fields.Boolean(string="Odoo Proxy Mode", compute="_compute_deployment_status")
    deployment_webhook_received = fields.Boolean(string="Webhook Receiving Confirmed", compute="_compute_deployment_status")
    deployment_signature_verified = fields.Boolean(string="Signature Verification Confirmed", compute="_compute_deployment_status")
    deployment_status = fields.Selection([
        ("ready", "Ready"),
        ("warning", "Needs Attention"),
        ("blocked", "Not Ready"),
    ], string="Deployment Status", compute="_compute_deployment_status")
    deployment_note = fields.Text(string="Deployment Notes", compute="_compute_deployment_status")

    workspace_ids = fields.One2many('bird.workspace', 'organization_id', string='Workspaces')
    channel_ids = fields.One2many('bird.channel', compute='_compute_bird_items', string='Channels')
    template_ids = fields.One2many('bird.template', compute='_compute_bird_items', string='Templates')

    @api.depends("webhook_token", "webhook_base_url")
    def _compute_webhook_public_url(self):
        system_base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
        for rec in self:
            base_url = (rec.webhook_base_url or system_base_url or "").strip().rstrip("/")
            rec.webhook_public_url = (
                f"{base_url}/bird/webhook/{rec.id}/{rec.webhook_token}"
                if rec.id and rec.webhook_token and base_url else False
            )
            rec.webhook_https_ready = bool(rec.webhook_public_url and rec.webhook_public_url.startswith("https://"))

    def _compute_webhook_counts(self):
        for rec in self:
            rec.webhook_subscription_count = len(rec.webhook_subscription_ids)
            rec.webhook_event_count = len(rec.webhook_event_ids)

    @api.depends(
        "webhook_token",
        "webhook_base_url",
        "webhook_verify_signatures",
        "webhook_deployment_mode",
        "webhook_event_ids",
        "webhook_event_ids.signature_valid",
    )
    def _compute_deployment_status(self):
        """Evaluate deployment health without hard-coding a database, domain or port.

        A key portability detail is that the Odoo worker serving the UI is not
        necessarily the worker receiving Bird webhooks. On multi-database
        installations a reverse proxy may send /bird/webhook/* to a dedicated
        Odoo instance with its own dbfilter. Therefore a successfully stored
        webhook event is valid routing evidence even when tools.config on the
        current UI worker has no dbfilter.
        """
        import re

        db_name = self.env.cr.dbname or ""
        configured_db_name = tools.config.get("db_name")
        dbfilter = tools.config.get("dbfilter") or ""
        proxy_mode = bool(tools.config.get("proxy_mode"))

        if isinstance(configured_db_name, (list, tuple)):
            configured_names = [str(x).strip() for x in configured_db_name if x]
        else:
            configured_names = [
                x.strip() for x in str(configured_db_name or "").split(",") if x.strip()
            ]

        name_match = bool(configured_names and db_name in configured_names)
        filter_match = False
        if dbfilter:
            try:
                filter_match = bool(re.match(dbfilter, db_name))
            except re.error:
                filter_match = False

        explicit_routing = bool(name_match or filter_match)

        for rec in self:
            received = bool(rec.webhook_event_ids)
            verified = bool(rec.webhook_event_ids.filtered("signature_valid"))
            mode = rec.webhook_deployment_mode or "auto"

            # A received event proves that a public Bird request reached this
            # database, regardless of which Odoo worker handled the UI page.
            runtime_proof = received

            if mode == "single_db":
                db_routing_ready = explicit_routing
                route_source = (
                    "db_name / dbfilter" if explicit_routing else "No matching db_name / dbfilter"
                )
            elif mode == "dedicated":
                db_routing_ready = bool(runtime_proof or explicit_routing)
                route_source = (
                    "Received webhook on this database" if runtime_proof
                    else ("Dedicated worker db_name / dbfilter" if explicit_routing else "Awaiting webhook proof")
                )
            elif mode == "external_proxy":
                db_routing_ready = runtime_proof
                route_source = (
                    "Received webhook through external routing" if runtime_proof else "Awaiting webhook proof"
                )
            else:  # auto
                db_routing_ready = bool(explicit_routing or runtime_proof)
                route_source = (
                    "db_name / dbfilter" if explicit_routing
                    else ("Received webhook on this database" if runtime_proof else "No routing evidence yet")
                )

            notes = []
            if not rec.webhook_https_ready:
                notes.append("Set a public HTTPS Webhook Base URL.")

            if not db_routing_ready:
                if mode == "single_db":
                    notes.append(
                        "Configure dbfilter or db_name so stateless Bird requests are routed to database %s." % db_name
                    )
                elif mode == "dedicated":
                    notes.append(
                        "Route /bird/webhook/ to a dedicated Odoo instance that selects this database, then send a test webhook."
                    )
                elif mode == "external_proxy":
                    notes.append(
                        "Configure the external proxy/gateway to route /bird/webhook/ to this database, then send a test webhook."
                    )
                else:
                    notes.append(
                        "No database routing proof yet. Use db_name/dbfilter, a dedicated webhook instance, or external proxy routing."
                    )

            # proxy_mode is recommended for deployments behind a reverse proxy,
            # but it is not itself proof that webhook routing is broken.
            if not proxy_mode:
                notes.append(
                    "Odoo proxy_mode is disabled. This is recommended behind Nginx, but it does not block webhook readiness when routing is otherwise proven."
                )
            if not received:
                notes.append("No Bird webhook event has been received on this database yet.")
            if rec.webhook_verify_signatures and received and not verified:
                notes.append("No received webhook has passed Bird signature verification yet.")

            blocked = not rec.webhook_https_ready or not db_routing_ready
            signature_warning = rec.webhook_verify_signatures and received and not verified
            warning = (not proxy_mode) or (not received) or signature_warning

            rec.deployment_db_name = db_name
            rec.deployment_dbfilter = dbfilter or False
            rec.deployment_db_routing_ready = db_routing_ready
            rec.deployment_route_source = route_source
            rec.deployment_proxy_mode = proxy_mode
            rec.deployment_webhook_received = received
            rec.deployment_signature_verified = verified
            rec.deployment_status = "blocked" if blocked else ("warning" if warning else "ready")
            rec.deployment_note = "\n".join(notes) if notes else "Webhook deployment checks passed."

    def action_check_webhook_deployment(self):
        self.ensure_one()
        # Computed fields are evaluated again after the form reloads. Keep the
        # action intentionally simple to avoid client-side action errors.
        return {"type": "ir.actions.client", "tag": "reload"}

    def _ensure_webhook_secrets(self):
        import secrets, base64
        for rec in self:
            vals = {}
            if not rec.webhook_token:
                vals["webhook_token"] = secrets.token_urlsafe(32)
            if not rec.webhook_signing_key:
                vals["webhook_signing_key"] = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
            if vals:
                rec.sudo().write(vals)
        return True

    def action_setup_webhooks(self):
        self.ensure_one()
        self._ensure_webhook_secrets()
        if not self.webhook_https_ready:
            raise UserError(
                "Bird requires a public HTTPS webhook URL. Set Webhook Base URL on this organization "
                "to the public HTTPS address of this Odoo server, or configure the web.base.url system parameter."
            )
        channels = self.channel_ids.filtered(lambda c: c.channel_type == "whatsapp" and c.state == "connected")
        if not channels:
            raise UserError("No connected WhatsApp channels were found for this organization.")
        Webhook = self.env["bird.webhook.subscription"].sudo()
        created = 0
        for channel in channels:
            for event_name in ("whatsapp.inbound", "whatsapp.outbound", "whatsapp.interaction"):
                local = Webhook.search([
                    ("organization_id", "=", self.id),
                    ("channel_id", "=", channel.id),
                    ("event", "=", event_name),
                    ("managed_by_connector", "=", True),
                ], limit=1)
                if local and local.bird_subscription_id:
                    continue
                payload = {
                    "service": "channels",
                    "event": event_name,
                    "url": self.webhook_public_url,
                    "signingKey": self.webhook_signing_key,
                    "eventFilters": [{"key": "channelId", "value": channel.channel_id}],
                }
                result = self.env["bird.api.service"].post(
                    path=f"/workspaces/{channel.workspace_id.workspace_id}/webhook-subscriptions",
                    access_key=self.access_key, payload=payload, timeout=self.request_timeout,
                )
                data = result.get("data") or {}
                if not result.get("ok"):
                    if local:
                        local.write({"status": "error", "last_error": result.get("error"), "raw_response": self.env["bird.api.service"].pretty_json(data)})
                    raise UserError("Bird webhook creation failed for %s (HTTP %s): %s" % (event_name, result.get("status_code"), result.get("error")))
                vals = {
                    "organization_id": self.id, "workspace_id": channel.workspace_id.id, "channel_id": channel.id,
                    "bird_subscription_id": data.get("id") or data.get("webhookSubscriptionId") or data.get("webhook_subscription_id"),
                    "service": "channels", "event": event_name, "webhook_url": self.webhook_public_url,
                    "signing_key": self.webhook_signing_key, "managed_by_connector": True,
                    "status": data.get("status") or "active",
                    "last_sync_at": fields.Datetime.now(), "last_error": False,
                    "raw_response": self.env["bird.api.service"].pretty_json(data),
                }
                if local:
                    local.write(vals)
                else:
                    Webhook.create(vals)
                created += 1
        # Reload directly. The previous nested ``next`` act_window caused an
        # OWL client error (undefined.map) after the backend had already
        # created the subscriptions successfully.
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_sync_webhooks(self):
        self.ensure_one()
        result = self.env["bird.api.service"].get(
            path=f"/workspaces/{self.workspace_id}/webhook-subscriptions",
            access_key=self.access_key,
            params={"limit": 100},
            timeout=self.request_timeout,
        )
        if not result.get("ok"):
            raise UserError(
                "Bird webhook sync failed (HTTP %s): %s"
                % (result.get("status_code"), result.get("error"))
            )

        data = result.get("data") or {}
        rows = data.get("results") if isinstance(data, dict) else data
        rows = rows if isinstance(rows, list) else []

        Webhook = self.env["bird.webhook.subscription"].sudo()
        seen_remote_ids = set()
        synced = 0
        external = 0
        managed = 0

        for row in rows:
            sub_id = row.get("id") or row.get("webhookSubscriptionId")
            event_name = row.get("event")
            if not sub_id or event_name not in (
                "whatsapp.inbound",
                "whatsapp.outbound",
                "whatsapp.interaction",
            ):
                continue

            seen_remote_ids.add(str(sub_id))
            channel_ext = False
            for event_filter in row.get("eventFilters") or []:
                if event_filter.get("key") == "channelId":
                    channel_ext = event_filter.get("value")
                    break

            channel = (
                self.env["bird.channel"].sudo().search(
                    [
                        ("organization_id", "=", self.id),
                        ("channel_id", "=", channel_ext),
                    ],
                    limit=1,
                )
                if channel_ext else False
            )

            remote_url = (row.get("url") or "").strip()
            is_managed = bool(
                remote_url
                and self.webhook_public_url
                and remote_url.rstrip("/") == self.webhook_public_url.rstrip("/")
            )

            local = Webhook.search(
                [
                    ("organization_id", "=", self.id),
                    ("bird_subscription_id", "=", str(sub_id)),
                ],
                limit=1,
            )
            vals = {
                "organization_id": self.id,
                "workspace_id": channel.workspace_id.id if channel else self.workspace_ids[:1].id,
                "channel_id": channel.id if channel else False,
                "bird_subscription_id": str(sub_id),
                "service": row.get("service") or "channels",
                "event": event_name,
                "webhook_url": remote_url or self.webhook_public_url,
                # Bird does not return the signing key when listing subscriptions.
                # Preserve our key only for subscriptions owned by this connector.
                "signing_key": self.webhook_signing_key if is_managed else False,
                "managed_by_connector": is_managed,
                "status": row.get("status") or "active",
                "last_sync_at": fields.Datetime.now(),
                "last_error": row.get("statusReason") or False,
                "raw_response": (
                    self.env["bird.api.service"].pretty_json(row)
                    if self.keep_api_responses else False
                ),
            }
            if local:
                local.write(vals)
            elif vals["workspace_id"]:
                Webhook.create(vals)

            synced += 1
            if is_managed:
                managed += 1
            else:
                external += 1

        # Do not delete missing subscriptions automatically; a paginated or
        # temporarily filtered Bird response should never destroy audit history.
        message = (
            "Synchronized %s webhook subscription(s): %s managed by this Odoo connector, "
            "%s external/existing."
            % (synced, managed, external)
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Bird Webhooks",
                "message": message,
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "bird.organization",
                    "res_id": self.id,
                    "view_mode": "form",
                    "target": "current",
                },
            },
        }

    @api.depends("wallet_balance", "low_balance_threshold", "low_balance_notifications")
    def _compute_low_balance_warning(self):
        for rec in self:
            rec.low_balance_warning = bool(
                rec.low_balance_notifications
                and rec.low_balance_threshold > 0
                and rec.wallet_balance < rec.low_balance_threshold
            )

    @api.constrains("template_sync_interval", "message_status_interval", "balance_refresh_interval", "request_timeout")
    def _check_configuration_intervals(self):
        for rec in self:
            if rec.template_sync_interval < 5:
                raise UserError("Bird Sync Interval must be at least 5 minutes.")
            if rec.message_status_interval < 5:
                raise UserError("Message Status Interval must be at least 5 minutes.")
            if rec.balance_refresh_interval < 5:
                raise UserError("Balance Refresh Interval must be at least 5 minutes.")
            if rec.request_timeout < 1:
                raise UserError("API Request Timeout must be at least 1 second.")

    def _is_due(self, last_run, interval_minutes, now=None):
        now = now or fields.Datetime.now()
        if not last_run:
            return True
        return now - last_run >= timedelta(minutes=max(int(interval_minutes or 5), 5))

    @api.model
    def _migrate_legacy_configuration(self):
        """Move V1.8.x global configuration values onto each Bird Organization once."""
        config = False
        if "bird.configuration" in self.env:
            config = self.env["bird.configuration"].sudo().search([("active", "=", True)], order="id desc", limit=1)
        params = self.env["ir.config_parameter"].sudo()

        def pbool(key, default=False):
            value = params.get_param(key)
            if value in (None, ""):
                return default
            return str(value).strip().lower() in ("1", "true", "yes", "on")

        def pint(key, default):
            value = params.get_param(key)
            try:
                return max(int(value), 1) if value not in (None, "") else default
            except Exception:
                return default

        for org in self.sudo().search([("legacy_configuration_migrated", "=", False)]):
            vals = {
                "auto_sync_templates": config.auto_sync_templates if config else pbool("bird.auto_sync_templates", False),
                "template_sync_interval": config.template_sync_interval if config else pint("bird.template_sync_interval", 30),
                "auto_refresh_message_status": config.auto_refresh_message_status if config else pbool("bird.auto_refresh_message_status", True),
                "message_status_interval": config.message_status_interval if config else pint("bird.message_status_interval", 10),
                "auto_refresh_balance": config.auto_refresh_balance if config else pbool("bird.auto_refresh_balance", False),
                "balance_refresh_interval": config.balance_refresh_interval if config else pint("bird.balance_refresh_interval", 60),
                "low_balance_notifications": config.low_balance_notifications if config else pbool("bird.low_balance_notifications", True),
                "default_locale": config.default_locale if config else (params.get_param("bird.default_locale") or "en"),
                "request_timeout": config.request_timeout if config else pint("bird.request_timeout", 20),
                "keep_api_responses": config.keep_api_responses if config else pbool("bird.keep_api_responses", True),
                "legacy_configuration_migrated": True,
            }
            vals["template_sync_interval"] = max(vals["template_sync_interval"], 5)
            vals["message_status_interval"] = max(vals["message_status_interval"], 5)
            vals["balance_refresh_interval"] = max(vals["balance_refresh_interval"], 5)
            org.write(vals)

        for xmlid in (
            "bird_connector.ir_cron_bird_sync_connector",
            "bird_connector.ir_cron_bird_refresh_message_status",
            "bird_connector.ir_cron_bird_refresh_balance",
        ):
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            if cron:
                cron.sudo().write({"active": True, "interval_number": 5, "interval_type": "minutes"})
        return True

    def action_clean_duplicate_templates(self):
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

    @api.depends('workspace_ids.channel_ids', 'workspace_ids.template_ids')
    def _compute_bird_items(self):
        for rec in self:
            workspaces = rec.workspace_ids
            rec.channel_ids = workspaces.mapped('channel_ids')
            
            template_fields = self.env['bird.template']._fields
            w_field = 'workspace_id'
            if 'workspace_id' not in template_fields and 'bird_workspace_id' in template_fields:
                w_field = 'bird_workspace_id'
            elif 'workspace_id' not in template_fields and 'workspace' in template_fields:
                w_field = 'workspace'
                
            rec.template_ids = self.env['bird.template'].sudo().search([(w_field, 'in', workspaces.ids)])


    def _wallets_from_response(self, payload):
        """Normalize Bird's GET /organizations/{id}/wallets response to a wallet list."""
        if isinstance(payload, list):
            return [w for w in payload if isinstance(w, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("results", "items", "wallets", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [w for w in value if isinstance(w, dict)]
        # Be tolerant if Bird returns one wallet object directly.
        if payload.get("walletId") or payload.get("id"):
            return [payload]
        return []

    def _bird_money_to_decimal(self, money):
        """Convert Bird money format {amount, exponent} into a decimal major-unit amount."""
        if not isinstance(money, dict):
            return None, None
        raw_amount = money.get("amount")
        exponent = money.get("exponent", 0)
        currency = money.get("currencyCode") or money.get("currency")
        if raw_amount is None:
            return None, currency
        try:
            amount = Decimal(str(raw_amount)) * (Decimal(10) ** int(exponent or 0))
        except (InvalidOperation, ValueError, TypeError):
            return None, currency
        return amount, currency

    def _fetch_bird_wallets(self):
        self.ensure_one()
        wallet_key = (self.wallet_api_key or self.access_key or '').strip()
        if not wallet_key:
            raise UserError("Configure a Wallet API Key (or Workspace Access Key fallback) first.")
        if not self.bird_id:
            raise UserError(
                "Organization ID is required. Copy the UUID from Bird > Settings > Organization > Company profile."
            )

        url = "https://api.bird.com/organizations/%s/wallets" % self.bird_id.strip()
        headers = {
            "Authorization": "AccessKey %s" % wallet_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            response = requests.get(url, headers=headers, timeout=self.request_timeout)
        except Exception as exc:
            raise UserError("Bird Wallet request failed: %s" % exc)

        try:
            payload = response.json()
        except Exception:
            payload = {"raw": response.text[:4000]}

        # Keep the raw response only when organization-level debugging is enabled.
        self.wallet_usage_raw = (
            json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            if self.keep_api_responses else False
        )

        if response.status_code != 200:
            extra = ''
            if response.status_code == 403:
                extra = (
                    "\n\nThe request reached Bird but this key cannot read organization wallets. "
                    "Use the Organization-level API key that succeeds against GET /organizations/{organizationId}/wallets."
                )
            elif response.status_code == 401:
                extra = "\n\nThe Wallet API Key was not accepted by Bird. Check the key value/type."
            raise UserError(
                "Bird Wallet API failed (HTTP %s).\n\nEndpoint: %s\n\nResponse:\n%s%s"
                % (
                    response.status_code,
                    url,
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str)[:5000],
                    extra,
                )
            )
        return payload, url

    def action_sync_balance(self):
        self.ensure_one()
        payload, _url = self._fetch_bird_wallets()
        wallets = self._wallets_from_response(payload)
        if not wallets:
            raise UserError(
                "Bird returned HTTP 200, but no wallet records were found in the response. "
                "The raw payload is saved in Wallet API Response."
            )

        selected = None
        configured_wallet_id = (self.wallet_id or '').strip()
        if configured_wallet_id:
            selected = next(
                (w for w in wallets if str(w.get("walletId") or w.get("id") or '') == configured_wallet_id),
                None,
            )
        if not selected:
            selected = next((w for w in wallets if w.get("isMain") is True), None)
        if not selected and len(wallets) == 1:
            selected = wallets[0]
        if not selected:
            raise UserError(
                "Bird returned multiple wallets, but none matched Wallet ID and no main wallet was marked. "
                "Check Wallet API Response and configure the required Wallet ID."
            )

        balance, currency = self._bird_money_to_decimal(selected.get("balance"))
        if balance is None:
            raise UserError(
                "The selected Bird wallet does not contain a valid balance.amount/exponent structure. "
                "The raw payload is saved in Wallet API Response."
            )

        wallet_id = str(selected.get("walletId") or selected.get("id") or configured_wallet_id or '')
        wallet_name = selected.get("name") or ("Main wallet" if selected.get("isMain") else False)
        currency = currency or self.currency_code or "EUR"

        self.write({
            "wallet_id": wallet_id or self.wallet_id,
            "wallet_name": wallet_name,
            "wallet_balance": float(balance),
            "currency_code": currency,
            "last_balance_sync": fields.Datetime.now(),
            "balance_source": "bird_wallet",
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Balance Updated",
                "message": "%s: %.2f %s" % (wallet_name or "Bird wallet", float(balance), currency),
                "type": "success",
                "sticky": False,
                # Refresh the Odoo form data after the successful server-side write.
                # This avoids a manual browser/F5 refresh.
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def action_test_connection(self):
        self.ensure_one()
        if not self.access_key or not self.workspace_id:
            raise UserError("Please ensure both Access Key and Workspace ID are filled.")
        url = f"https://api.bird.com/workspaces/{self.workspace_id}/connectors"
        headers = {"Authorization": f"AccessKey {self.access_key}", "Content-Type": "application/json"}
        try:
            response = requests.get(url, headers=headers, timeout=self.request_timeout)
            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {'title': 'Connection Successful', 'message': 'Successfully connected to Bird.com API.', 'type': 'success', 'sticky': False}
                }
            else:
                raise UserError(f"Connection Failed: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            raise UserError(f"Network Connection Error: {str(e)}")

    def _bird_template_effective_status(self, item):
        """Return a normalized Bird template/version status for ranking and UI."""
        status = str((item or {}).get("status") or (item or {}).get("state") or "draft").lower()
        approvals = []
        for content in (item or {}).get("platformContent") or []:
            if isinstance(content, dict):
                approvals += content.get("approvals") or []
        approval_status = next(
            (str(a.get("status") or "").lower() for a in approvals if isinstance(a, dict) and a.get("status")),
            "",
        )
        if approval_status:
            status = approval_status
        if status == "approved":
            status = "active"
        if status not in ("active", "pending", "draft", "rejected", "inactive"):
            status = "draft"
        return status

    def _upsert_synced_version(self, template, item):
        """Keep Bird versions under the canonical Odoo template instead of creating duplicate templates."""
        if not template or not isinstance(item, dict):
            return
        vid = item.get("id") or item.get("channelTemplateId") or item.get("resourceId") or item.get("versionId")
        if not vid:
            return
        status = self._bird_template_effective_status(item)
        raw_dt = item.get("updatedAt") or item.get("lastUpdated") or item.get("modifiedAt")
        parsed_dt = False
        if raw_dt:
            try:
                from datetime import datetime, timezone
                parsed_dt = datetime.fromisoformat(str(raw_dt).replace("Z", "+00:00"))
                if parsed_dt.tzinfo:
                    parsed_dt = parsed_dt.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                parsed_dt = False
        vals = {
            "template_id": template.id,
            "bird_version_id": vid,
            "description": item.get("description") or item.get("name") or template.name,
            "status": status if status in ("draft", "pending", "active", "approved", "inactive", "rejected") else "draft",
            "publisher": item.get("publisherName") or item.get("publishedBy") or item.get("createdBy") or "",
            "last_updated": parsed_dt,
            "last_updated_by": item.get("updatedByName") or item.get("lastUpdatedBy") or item.get("updatedBy") or "",
            "is_current": bool(status == "active" or vid == template.bird_template_id or vid == template.active_resource_id),
            "raw_json": json.dumps(item, ensure_ascii=False, indent=2),
        }
        Version = self.env["bird.template.version"].sudo()
        existing = Version.search([("template_id", "=", template.id), ("bird_version_id", "=", vid)], limit=1)
        if existing:
            existing.write(vals)
        else:
            Version.create(vals)

    @api.model
    def _cron_sync_connector_data(self):
        """Dispatcher: each organization controls whether and when its own sync runs."""
        now = fields.Datetime.now()
        for org in self.sudo().search([("state", "=", "active"), ("auto_sync_templates", "=", True)]):
            if not org._is_due(org.last_auto_sync, org.template_sync_interval, now=now):
                continue
            try:
                org.action_sync_workspaces_and_channels(target_workspace_id=org.workspace_id)
                org.write({"last_auto_sync": now})
            except Exception:
                _logger.exception("Bird automatic connector sync failed for organization %s", org.display_name)
        return True

    @api.model
    def _cron_refresh_wallet_balances(self):
        """Dispatcher: each organization controls whether and when its wallet refresh runs."""
        now = fields.Datetime.now()
        for org in self.sudo().search([("state", "=", "active"), ("auto_refresh_balance", "=", True)]):
            if not org._is_due(org.last_auto_balance_refresh, org.balance_refresh_interval, now=now):
                continue
            try:
                org.action_sync_balance()
                org.write({"last_auto_balance_refresh": now})
            except Exception:
                _logger.exception("Bird automatic balance refresh failed for organization %s", org.display_name)
        return True

    def action_sync_workspaces_and_channels(self, target_workspace_id=False):
        self.ensure_one()

        
        
        access_key = self.access_key
        api_workspace_id = target_workspace_id or self.workspace_id
        
        if not access_key or not api_workspace_id:
            raise UserError("Missing API Access Key or Workspace ID configuration.")

        headers = {
            "Authorization": f"AccessKey {access_key}",
            "Content-Type": "application/json"
        }

        local_workspace = self.env['bird.workspace'].sudo().search([('workspace_id', '=', api_workspace_id)], limit=1)
        if not local_workspace:
            local_workspace = self.env['bird.workspace'].sudo().create({
                'name': self.name or 'Bird Workspace',
                'workspace_id': api_workspace_id,
                'organization_id': self.id,
                'state': 'active'
            })

        channels_created = 0
        templates_created = 0

        # 1. Sync Channels
        channels_url = f"https://api.bird.com/workspaces/{api_workspace_id}/channels"
        try:
            c_response = requests.get(channels_url, headers=headers, timeout=self.request_timeout)
            if c_response.status_code == 200:
                c_data = c_response.json()
                for channel_info in c_data.get('results', []):
                    if channel_info.get('platformId') == 'whatsapp':
                        existing_channel = self.env['bird.channel'].sudo().search([('channel_id', '=', channel_info.get('id'))], limit=1)
                        if not existing_channel:
                            state_field = self.env['bird.channel']._fields.get('state')
                            allowed_states = [sel[0] for sel in state_field.selection] if state_field and hasattr(state_field, 'selection') else []
                            
                            target_state = 'active'
                            if allowed_states:
                                if 'active' not in allowed_states:
                                    if 'Active' in allowed_states:
                                        target_state = 'Active'
                                    elif 'enabled' in allowed_states:
                                        target_state = 'enabled'
                                    elif 'Enabled' in allowed_states:
                                        target_state = 'Enabled'
                                    else:
                                        target_state = allowed_states[0]

                            self.env['bird.channel'].sudo().create({
                                'name': channel_info.get('name', 'WhatsApp Channel'),
                                'channel_id': channel_info.get('id'),
                                'channel_type': 'whatsapp',
                                'workspace_id': local_workspace.id,
                                'state': target_state
                            })
                            channels_created += 1
        except Exception as e:
            _logger.error(f"Channels Sync Error: {str(e)}")

        # 2. Sync Touchpoints Templates with Full Details
        projects_url = f"https://api.bird.com/workspaces/{api_workspace_id}/projects"
        project_ids = []
        try:
            p_response = requests.get(projects_url, headers=headers, timeout=self.request_timeout)
            if p_response.status_code == 200:
                p_data = p_response.json()
                project_list = p_data.get('results') or p_data.get('items') or []
                if not project_list and isinstance(p_data, list):
                    project_list = p_data
                project_ids = [p.get('id') for p in project_list if p.get('id')]
        except Exception as e:
            _logger.error(f"Projects Fetch Error: {str(e)}")

        locale_field = self.env['bird.template']._fields.get('locale')
        allowed_locales = [sel[0] for sel in locale_field.selection] if locale_field and hasattr(locale_field, 'selection') else []

        for proj_id in project_ids:
            templates_url = f"https://api.bird.com/workspaces/{api_workspace_id}/projects/{proj_id}/channel-templates"
            try:
                t_response = requests.get(templates_url, headers=headers, timeout=self.request_timeout)
                _logger.info(f"Bird Touchpoints Templates API status for project {proj_id}: {t_response.status_code}")
                
                if t_response.status_code == 200:
                    t_data = t_response.json()
                    template_list = t_data.get('results') or t_data.get('items') or []
                    if not template_list and isinstance(t_data, list):
                        template_list = t_data

                    # One Bird Project can have many versions.  Keep one canonical
                    # bird.template record and store every other resource as a
                    # bird.template.version.  Prefer Active > Pending > Draft > Rejected/Inactive.
                    status_rank = {"active": 50, "pending": 40, "draft": 30, "rejected": 20, "inactive": 10}
                    template_list = sorted(
                        [x for x in template_list if isinstance(x, dict)],
                        key=lambda x: status_rank.get(self._bird_template_effective_status(x), 0),
                        reverse=True,
                    )
                    project_template_record = False

                    for template_info in template_list:
                        template_id = template_info.get('id')
                        if not template_id:
                            continue

                        t_name = template_info.get('name') or template_info.get('description') or template_id
                        deployments = template_info.get('deployments', [])
                        for dep in deployments:
                            if dep.get('key') == 'whatsappTemplateName' and dep.get('value'):
                                t_name = dep.get('value')
                                break

                        raw_locale = template_info.get('defaultLocale', 'en')
                        sanitized_locale = raw_locale.replace('-', '_') if raw_locale else 'en'
                        if allowed_locales and sanitized_locale not in allowed_locales:
                            short_locale = sanitized_locale.split('_')[0]
                            sanitized_locale = short_locale if short_locale in allowed_locales else (allowed_locales[0] if allowed_locales else 'en')

                        # تعريف متغيرات المعاينة مسبقاً لمنع UnboundLocalError
                        body_text = ""
                        footer_text = ""
                        header_image_url = ""
                        preview_header_image_binary = False

                        platform_content = template_info.get('platformContent', [])
                        if platform_content and isinstance(platform_content, list):
                            blocks = platform_content[0].get('blocks', [])
                            for block in blocks:
                                b_type = block.get('type')
                                role = block.get('role')
                                
                                # 1. Check for nested header object inside the block
                                header_obj = block.get('header', {})
                                if header_obj and isinstance(header_obj, dict):
                                    if header_obj.get('type') == 'image':
                                        img_obj = header_obj.get('image', {})
                                        header_image_url = img_obj.get('mediaUrl') or img_obj.get('url', '')

                                # 2. Standard Templates (Text / Image)
                                if b_type in ['text', 'image']:
                                    if role == 'body':
                                        body_text = block.get('text', {}).get('text', '')
                                    elif role == 'footer':
                                        footer_text = block.get('text', {}).get('text', '')
                                    elif role == 'header' and b_type == 'image':
                                        img_obj = block.get('image', {})
                                        header_image_url = img_obj.get('mediaUrl') or img_obj.get('url', '')

                                # Interactive WhatsApp Flow Templates
                                elif b_type == 'whatsapp-flow':
                                    flow_data = block.get('whatsappFlow', {})
                                    body_text = flow_data.get('body', {}).get('text', {}).get('text', '')
                                    footer_text = flow_data.get('footer', {}).get('text', {}).get('text', '')
                                    
                                    header_obj = flow_data.get('header', {})
                                    if header_obj and header_obj.get('type') == 'image':
                                        img_obj = header_obj.get('image', {})
                                        header_image_url = img_obj.get('mediaUrl') or img_obj.get('url', '')

                        # تحميل الصورة بواسطة AccessKey وتغليفها كـ Base64
                        if header_image_url:
                            try:
                                img_res = requests.get(header_image_url, headers=headers, timeout=self.request_timeout)
                                if img_res.status_code == 200:
                                    preview_header_image_binary = base64.b64encode(img_res.content)
                            except Exception as e:
                                _logger.error(f"Preview image download error: {e}")

                        # تجهيز قائمة الحقول والتفاصيل كاملة
                        template_vals = {
                            'name': t_name,
                            'bird_template_id': template_id,
                            'project_id': template_info.get('projectId', proj_id),
                            'version': str(template_info.get('version', '1')),
                            'locale': sanitized_locale,
                            'status': self._bird_template_effective_status(template_info) if self._bird_template_effective_status(template_info) in ('active','draft','pending','rejected') else 'draft',
                            'source': 'bird',
                            'last_status_sync': fields.Datetime.now(),
                            'description': template_info.get('description', ''),
                            'supported_platforms': str(template_info.get('supportedPlatforms', [])),
                            'is_cloneable': template_info.get('isCloneable', False),
                            'short_links_enabled': template_info.get('shortLinks', {}).get('enabled', False),
                            'short_links_domain': template_info.get('shortLinks', {}).get('domain', ''),
                            'platform_info': json.dumps(template_info.get('platformInfo', {}), indent=2),
                            'platform_content': json.dumps(template_info.get('platformContent', []), indent=2),
                            'deployments': json.dumps(template_info.get('deployments', []), indent=2),
                            'styles': json.dumps(template_info.get('styles', []), indent=2),
                            'variables': json.dumps(template_info.get('variables', []), indent=2),
                            'generic_content': json.dumps(template_info.get('genericContent', []), indent=2),
                            'preview_body_text': body_text,
                            'preview_footer_text': footer_text,
                            'preview_header_image': preview_header_image_binary,
                        }
                        # Use the centralized resilient preview parser. It handles
                        # image/text headers, RTL body/footer and interactive buttons.
                        template_vals.update(
                            self.env['bird.template']._extract_preview_from_payload(template_info, access_key)
                        )

                        template_fields = self.env['bird.template']._fields
                        workspace_field_name = 'workspace_id'
                        if 'workspace_id' not in template_fields:
                            if 'bird_workspace_id' in template_fields:
                                workspace_field_name = 'bird_workspace_id'
                            elif 'workspace' in template_fields:
                                workspace_field_name = 'workspace'

                        # The first (highest-ranked) version becomes the canonical
                        # template. Remaining resources are recorded as versions only.
                        if not project_template_record:
                            existing_template = self.env['bird.template'].sudo().search([
                                ('project_id', '=', proj_id),
                                (workspace_field_name, '=', local_workspace.id),
                            ], limit=1)
                            if not existing_template:
                                existing_template = self.env['bird.template'].sudo().search([
                                    ('bird_template_id', '=', template_id),
                                    (workspace_field_name, '=', local_workspace.id),
                                ], limit=1)

                            final_vals = {k: v for k, v in template_vals.items() if k in template_fields}
                            final_vals[workspace_field_name] = local_workspace.id

                            if existing_template:
                                existing_template.sudo().write(final_vals)
                                project_template_record = existing_template
                            else:
                                project_template_record = self.env['bird.template'].sudo().create(final_vals)
                                templates_created += 1

                        self._upsert_synced_version(project_template_record, template_info)

            except Exception as e:
                _logger.error(f"Templates Sync Error for project {proj_id}: {str(e)}")

        # Consolidate historical/project-version duplicates after a successful
        # synchronization.  The cleanup preserves message/version references.
        try:
            self.env['bird.template'].sudo()._cleanup_duplicate_projects()
        except Exception:
            _logger.exception('Bird template duplicate cleanup failed after sync')

        # Direct organization-form sync: refresh the current view so newly
        # synchronized channels/templates appear immediately. Internal callers
        # pass target_workspace_id and keep the tuple return for compatibility.
        if not target_workspace_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Bird Sync Completed",
                    "message": "Channels created: %s, Templates created: %s" % (channels_created, templates_created),
                    "type": "success",
                    "sticky": False,
                    "next": {"type": "ir.actions.client", "tag": "reload"},
                },
            }
        return channels_created, templates_created