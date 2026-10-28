import json
import uuid
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import AccessDenied
from odoo.http import request


API_PREFIX = "/alezdhar/api/v1"


class AlezdharMobileApiV1(http.Controller):
    @staticmethod
    def _request_id():
        supplied = request.httprequest.headers.get("X-Request-ID", "")
        try:
            return str(uuid.UUID(supplied))
        except (ValueError, TypeError, AttributeError):
            return str(uuid.uuid4())

    @staticmethod
    def _response(status="success", data=None, error=None, code=200, request_id=None):
        payload = {
            "status": status,
            "data": data,
            "error": error,
            "request_id": request_id or AlezdharMobileApiV1._request_id(),
            "server_time": fields.Datetime.now().isoformat(),
            "schema_version": "1.0",
        }
        return request.make_json_response(payload, status=code)

    @staticmethod
    def _bearer_token():
        authorization = request.httprequest.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if separator != " " or scheme.casefold() != "bearer" or not token.strip():
            raise AccessDenied()
        return token.strip()

    @staticmethod
    def _authenticated_session():
        enabled = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("alezdhar_mobile.api_enabled", "False")
        )
        if enabled not in (True, "True", "1", 1):
            raise AccessDenied()
        return request.env["alezdhar.mobile.session"].authenticate_access_token(
            AlezdharMobileApiV1._bearer_token()
        )

    @http.route(
        API_PREFIX + "/health",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def health(self, **_kwargs):
        return self._response(
            data={"service": "alezdhar-mobile-api", "api_version": "v1"}
        )

    @http.route(
        API_PREFIX + "/bootstrap",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def bootstrap(self, **_kwargs):
        request_id = self._request_id()
        try:
            session = self._authenticated_session()
        except AccessDenied:
            return self._response(
                status="error",
                error={"code": "authentication_required", "message": "Authentication required."},
                code=401,
                request_id=request_id,
            )
        return self._response(
            data={
                "profile": session.identity_id.safe_profile_dto(),
                "features": request.env["alezdhar.mobile.feature"].bootstrap_dto(),
                "locale_defaults": {"primary": "ar", "supported": ["ar", "en"]},
                "routes": {"profile": API_PREFIX + "/me"},
            },
            request_id=request_id,
        )

    @http.route(
        API_PREFIX + "/me",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def me(self, **_kwargs):
        request_id = self._request_id()
        try:
            session = self._authenticated_session()
        except AccessDenied:
            return self._response(
                status="error",
                error={"code": "authentication_required", "message": "Authentication required."},
                code=401,
                request_id=request_id,
            )
        return self._response(
            data=session.identity_id.safe_profile_dto(), request_id=request_id
        )

    @http.route(
        API_PREFIX + "/auth/login",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def login(self, **_kwargs):
        request_id = self._request_id()
        provider = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("alezdhar_mobile.auth_provider", "disabled")
        )
        if provider != "password":
            return self._response(
                status="error",
                error={
                    "code": "authentication_provider_disabled",
                    "message": "Mobile authentication is not configured.",
                },
                code=503,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            installation_id = str(uuid.UUID(str(payload.get("installation_id", ""))))
            platform = payload.get("platform")
            if platform not in ("android", "ios"):
                raise ValueError()
            identity = request.env["alezdhar.mobile.identity"].authenticate_password(
                payload.get("login_identifier"), payload.get("password")
            )
            device = request.env["alezdhar.mobile.device"].sudo().search(
                [("installation_id", "=", installation_id)], limit=1
            )
            if device and (device.identity_id != identity or device.revoked_at):
                raise AccessDenied()
            if not device:
                device = request.env["alezdhar.mobile.device"].sudo().create(
                    {
                        "identity_id": identity.id,
                        "name": (payload.get("device_name") or "Mobile device")[:128],
                        "installation_id": installation_id,
                        "platform": platform,
                        "trusted": True,
                        "last_seen_at": fields.Datetime.now(),
                    }
                )
            else:
                device.sudo().write({"last_seen_at": fields.Datetime.now()})
            now = fields.Datetime.now()
            _session, access_token, refresh_token = request.env[
                "alezdhar.mobile.session"
            ].issue(
                identity,
                device,
                now + timedelta(minutes=15),
                now + timedelta(days=30),
            )
        except (AccessDenied, ValueError, TypeError, json.JSONDecodeError):
            return self._response(
                status="error",
                error={
                    "code": "invalid_credentials",
                    "message": "Employee number or password is invalid.",
                },
                code=401,
                request_id=request_id,
            )
        return self._response(
            data={
                "access_token": access_token,
                "access_expires_in": 900,
                "refresh_token": refresh_token,
                "refresh_expires_in": 2592000,
                "profile": identity.safe_profile_dto(),
            },
            request_id=request_id,
        )

    @http.route(
        API_PREFIX + "/auth/activate",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def activate(self, **_kwargs):
        return self._response(
            status="error",
            error={
                "code": "enrollment_provider_disabled",
                "message": "Mobile enrollment is not configured.",
            },
            code=503,
        )

    @http.route(
        API_PREFIX + "/auth/refresh", type="http", auth="public", methods=["POST"], csrf=False, save_session=False,
    )
    def refresh(self, **_kwargs):
        request_id = self._request_id()
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            now = fields.Datetime.now()
            session, access_token, refresh_token = request.env["alezdhar.mobile.session"].rotate_refresh_token(
                payload.get("refresh_token"), now + timedelta(minutes=15), now + timedelta(days=30)
            )
        except (AccessDenied, TypeError, json.JSONDecodeError):
            return self._response(
                status="error",
                error={"code": "invalid_refresh_token", "message": "The saved session has expired. Please sign in again."},
                code=401,
                request_id=request_id,
            )
        return self._response(
            data={"access_token": access_token, "access_expires_in": 900, "refresh_token": refresh_token,
                  "refresh_expires_in": 2592000, "profile": session.identity_id.safe_profile_dto()},
            request_id=request_id,
        )

