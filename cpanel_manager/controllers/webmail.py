from html import escape

from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class CpanelWebmailController(http.Controller):
    @http.route("/cpanel/webmail/<int:mailbox_id>", type="http", auth="user")
    def open_webmail(self, mailbox_id, **kwargs):
        if not request.env.user.has_group("cpanel_manager.group_cpanel_admin"):
            raise AccessError(_("Only cPanel administrators can open Webmail sessions."))
        mailbox = request.env["cpanel.mailbox"].browse(mailbox_id).exists()
        if not mailbox:
            return request.not_found()
        mailbox.check_access_rights("read")
        mailbox.check_access_rule("read")
        login, domain = mailbox.name.split("@", 1)
        access_route = request.httprequest.access_route
        remote_address = access_route[0] if access_route else request.httprequest.remote_addr
        data = mailbox.server_id._api_call(
            "Session",
            "create_webmail_session_for_mail_user",
            {"login": login, "domain": domain, "remote_address": remote_address},
        )
        if not isinstance(data, dict) or not data.get("session") or not data.get("token"):
            raise UserError(_("cPanel did not return a valid Webmail session."))
        hostname = data.get("hostname") or mailbox.server_id.host
        action = "https://%s:2096%s/login" % (hostname, data["token"])
        # cPanel requires a POST, so return a tiny auto-submitting page rather
        # than exposing mailbox passwords or storing them in Odoo.
        page = """<!doctype html><html><head><meta charset=\"utf-8\"><title>Webmail</title></head>
<body><p>Opening Webmail…</p><form id=\"webmail\" method=\"post\" action=\"%s\">
<input type=\"hidden\" name=\"session\" value=\"%s\"></form>
<script>document.getElementById('webmail').submit();</script></body></html>""" % (
            escape(action, quote=True),
            escape(str(data["session"]), quote=True),
        )
        return request.make_response(page, headers=[("Content-Type", "text/html; charset=utf-8")])
