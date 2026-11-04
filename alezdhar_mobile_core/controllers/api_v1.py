import json
import uuid
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import AccessDenied, ValidationError
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
        API_PREFIX + "/branding",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def branding(self, **_kwargs):
        return self._response(
            data=request.env["alezdhar.mobile.branding"].public_dto()
        )

    @http.route(
        API_PREFIX + "/tenant/resolve",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
        save_session=False,
    )
    def resolve_tenant(self, **_kwargs):
        request_id = self._request_id()
        code = (request.httprequest.args.get("company_code") or "").strip().upper()
        if not code and request.httprequest.method == "POST":
            try:
                body = json.loads(request.httprequest.get_data(as_text=True) or "{}")
                code = str(body.get("company_code") or "").strip().upper()
            except Exception:
                code = ""
        if not code:
            return self._response(
                status="error",
                error={"code": "missing_company_code", "message": "يرجى إدخال كود الشركة."},
                code=422,
                request_id=request_id,
            )
        sub = request.env["alezdhar.mobile.subscription"].sudo().search(
            [("company_code", "=", code)], limit=1
        )
        if not sub:
            return self._response(
                status="error",
                error={"code": "invalid_company_code", "message": "كود الشركة غير صحيح."},
                code=404,
                request_id=request_id,
            )
        try:
            request.env["alezdhar.mobile.subscription"].verify_company_subscription(
                sub.company_id, check_new_seat=False
            )
        except ValidationError as exc:
            return self._response(
                status="error",
                error={"code": "subscription_inactive", "message": str(exc)},
                code=403,
                request_id=request_id,
            )
        return self._response(
            data={
                "company_code": sub.company_code,
                "company_name": sub.name,
                "server_url": sub.server_url or "https://odoo-test.ezdharpos.com",
                "state": sub.state,
                "plan_type": sub.plan_type,
                "max_employees": sub.max_employees,
                "active_employees": sub.active_employees_count,
            },
            request_id=request_id,
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
        API_PREFIX + "/auth/enroll-face",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def enroll_face(self, **_kwargs):
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
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            session.identity_id.sudo().enroll_reference_face(payload.get("image_base64"))
            request.env["alezdhar.mobile.audit"].sudo().create({
                "identity_id": session.identity_id.id,
                "company_id": session.identity_id.company_id.id,
                "event_type": "face_reference_enrolled",
                "request_id": request_id,
                "outcome": "success",
                "metadata_json": json.dumps({
                    "employee_id": session.identity_id.employee_id.id,
                    "device_id": session.device_id.id,
                }, ensure_ascii=False),
            })
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            return self._response(
                status="error",
                error={"code": "face_enrollment_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )
        return self._response(
            data={"profile": session.identity_id.safe_profile_dto()},
            request_id=request_id,
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
            # Single-device binding enforcement: an employee may only bind one active phone.
            device_name = (payload.get("device_name") or "Mobile device")[:128]
            hardware_bound = bool(payload.get("hardware_bound"))
            active_bound_devices = request.env["alezdhar.mobile.device"].sudo().search([
                ("identity_id", "=", identity.id),
                ("revoked_at", "=", False),
                ("trusted", "=", True),
            ])
            if active_bound_devices and any(
                d.installation_id != installation_id for d in active_bound_devices
            ):
                # Automatic one-time migration from legacy random UUID ("Alezdhar Android")
                # to persistent hardware UUID on the employee's existing phone.
                existing_owner = request.env["alezdhar.mobile.device"].sudo().search(
                    [("installation_id", "=", installation_id)], limit=1
                )
                is_legacy_binding = all(
                    d.name in ("Alezdhar Android", "Alezdhar iOS", "Mobile device")
                    for d in active_bound_devices
                )
                if hardware_bound and is_legacy_binding and not existing_owner:
                    primary_device = active_bound_devices[0]
                    extra_devices = active_bound_devices - primary_device
                    if extra_devices:
                        extra_devices.action_revoke()
                    primary_device.sudo().write({
                        "installation_id": installation_id,
                        "name": device_name,
                        "last_seen_at": fields.Datetime.now(),
                    })
                else:
                    locale = (request.httprequest.headers.get("Accept-Language") or "ar").lower()
                    msg = (
                        "This account is already bound to another mobile device. Please contact HR to reset your bound device."
                        if locale.startswith("en")
                        else "هذا الحساب مرتبط بجوال آخر بالفعل ولا يمكن تسجيل الدخول من أكثر من جهاز. يرجى مراجعة الموارد البشرية لإعادة تعيين الجهاز."
                    )
                    return self._response(
                        status="error",
                        error={
                            "code": "device_already_bound",
                            "message": msg,
                        },
                        code=403,
                        request_id=request_id,
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
                        "name": device_name,
                        "installation_id": installation_id,
                        "platform": platform,
                        "trusted": True,
                        "last_seen_at": fields.Datetime.now(),
                    }
                )
            else:
                update_vals = {"last_seen_at": fields.Datetime.now()}
                if device_name not in ("Alezdhar Android", "Alezdhar iOS", "Mobile device"):
                    update_vals["name"] = device_name
                device.sudo().write(update_vals)
            now = fields.Datetime.now()
            # Revoke previous active sessions for this identity so only one session is active
            request.env["alezdhar.mobile.session"].sudo().search([
                ("identity_id", "=", identity.id),
                ("revoked_at", "=", False),
            ]).write({"revoked_at": now})
            _session, access_token, refresh_token = request.env[
                "alezdhar.mobile.session"
            ].issue(
                identity,
                device,
                now + timedelta(minutes=15),
                now + timedelta(days=30),
            )
        except AccessDenied as exc:
            err_msg = str(exc) if str(exc) and str(exc) != "Access Denied" else ""
            if "اشتراك" in err_msg:
                return self._response(
                    status="error",
                    error={
                        "code": "subscription_inactive",
                        "message": err_msg,
                    },
                    code=403,
                    request_id=request_id,
                )
            return self._response(
                status="error",
                error={
                    "code": "invalid_credentials",
                    "message": "Employee number or password is invalid.",
                },
                code=401,
                request_id=request_id,
            )
        except (ValueError, TypeError, json.JSONDecodeError):
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
