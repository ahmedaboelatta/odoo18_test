import json

from odoo import fields, http
from odoo.exceptions import AccessDenied
from odoo.http import request

from odoo.addons.alezdhar_mobile_core.controllers.api_v1 import API_PREFIX, AlezdharMobileApiV1


class AlezdharNotificationApiV1(http.Controller):
    @staticmethod
    def _session_or_error(request_id):
        try:
            return AlezdharMobileApiV1._authenticated_session(), None
        except AccessDenied:
            return None, AlezdharMobileApiV1._response(
                status="error", error={"code": "authentication_required", "message": "Authentication required."},
                code=401, request_id=request_id,
            )

    @http.route(API_PREFIX + "/notifications", type="http", auth="public", methods=["GET"], csrf=False, save_session=False)
    def notifications(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        Inbox = request.env["alezdhar.mobile.notification.inbox"].sudo()
        rows = Inbox.search([("identity_id", "=", session.identity_id.id)], limit=100)
        return AlezdharMobileApiV1._response(data={
            "items": [row.mobile_dto() for row in rows],
            "unread_count": len(rows.filtered(lambda row: not row.is_read)),
        }, request_id=request_id)

    @http.route(API_PREFIX + "/notifications/<int:notification_id>/read", type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def mark_read(self, notification_id, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        row = request.env["alezdhar.mobile.notification.inbox"].sudo().search([
            ("id", "=", notification_id), ("identity_id", "=", session.identity_id.id)
        ], limit=1)
        if not row:
            return AlezdharMobileApiV1._response(
                status="error", error={"code": "notification_not_found", "message": "Notification not found."},
                code=404, request_id=request_id,
            )
        if not row.is_read:
            row.write({"is_read": True, "read_at": fields.Datetime.now()})
        return AlezdharMobileApiV1._response(data=row.mobile_dto(), request_id=request_id)

    @http.route(API_PREFIX + "/notifications/device", type="http", auth="public",
                methods=["POST", "DELETE"], csrf=False, save_session=False)
    def register_device(self, **_kwargs):
        request_id = AlezdharMobileApiV1._request_id()
        session, error = self._session_or_error(request_id)
        if error:
            return error
        device = session.device_id.sudo()
        if request.httprequest.method == "DELETE":
            device.write({"push_installation_id": False, "push_enabled": False})
            return AlezdharMobileApiV1._response(data={"registered": False}, request_id=request_id)
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            fid = str(payload.get("installation_id") or "").strip()
            if not fid or len(fid) > 512:
                raise ValueError()
        except (ValueError, TypeError, json.JSONDecodeError):
            return AlezdharMobileApiV1._response(
                status="error", error={"code": "invalid_installation_id",
                "message": "A valid Firebase Installation ID is required."},
                code=400, request_id=request_id,
            )
        request.env["alezdhar.mobile.device"].sudo().search([
            ("push_installation_id", "=", fid), ("id", "!=", device.id)
        ]).write({"push_installation_id": False, "push_enabled": False})
        device.write({
            "push_installation_id": fid,
            "push_enabled": True,
            "push_registered_at": fields.Datetime.now(),
            "last_seen_at": fields.Datetime.now(),
        })
        return AlezdharMobileApiV1._response(data={"registered": True}, request_id=request_id)
