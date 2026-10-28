import uuid

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
        # Deliberately closed until a vetted provider/rate limiter is configured.
        return self._response(
            status="error",
            error={
                "code": "authentication_provider_disabled",
                "message": "Mobile authentication is not configured.",
            },
            code=503,
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

