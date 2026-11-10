import json
import urllib.parse
import urllib.request
import uuid
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import AccessDenied, ValidationError
from odoo.http import request


API_PREFIX = "/hader/api/v1"
LEGACY_API_PREFIX = "/alezdhar/api/v1"
DEFAULT_MASTER_SECRET = "HADER-SAAS-MASTER-2026-SECRET"


def api_routes(*subpaths):
    routes = []
    for sp in subpaths:
        routes.append(API_PREFIX + sp)
        routes.append(LEGACY_API_PREFIX + sp)
    return routes


class HaderMobileApiV1(http.Controller):
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
            "request_id": request_id or HaderMobileApiV1._request_id(),
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
            .get_param("hader_mobile.api_enabled", "False")
        )
        if enabled not in (True, "True", "1", 1):
            raise AccessDenied()
        return request.env["hader.mobile.session"].authenticate_access_token(
            HaderMobileApiV1._bearer_token()
        )

    @http.route(
        api_routes("/health"),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def health(self, **_kwargs):
        return self._response(
            data={"service": "hader-mobile-api", "api_version": "v1"}
        )

    @http.route(
        api_routes("/branding"),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=False,
    )
    def branding(self, **_kwargs):
        return self._response(
            data=request.env["hader.mobile.branding"].public_dto()
        )

    @http.route(
        api_routes("/tenant/resolve"),
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
        sub = request.env["hader.mobile.subscription"].sudo().search(
            [("company_code", "=", code)], limit=1
        )
        if not sub:
            # Fallback to Central SaaS Registry if not found locally and not already proxied
            if not request.httprequest.headers.get("X-Hader-Central-Lookup"):
                central_url = (
                    request.env["ir.config_parameter"]
                    .sudo()
                    .get_param("hader_mobile.central_saas_url", "https://odoo-test.ezdharpos.com/odoo20")
                )
                if central_url:
                    try:
                        lookup_url = f"{central_url.rstrip('/')}/hader/api/v1/tenant/resolve?company_code={urllib.parse.quote(code)}"
                        req = urllib.request.Request(
                            lookup_url,
                            headers={"X-Hader-Central-Lookup": "1", "Accept": "application/json"},
                        )
                        with urllib.request.urlopen(req, timeout=4) as resp:
                            remote_payload = json.loads(resp.read().decode("utf-8"))
                            if remote_payload.get("status") == "success" and remote_payload.get("data"):
                                return self._response(
                                    data=remote_payload["data"],
                                    request_id=request_id,
                                )
                    except Exception:
                        pass
            return self._response(
                status="error",
                error={"code": "invalid_company_code", "message": "كود الشركة غير صحيح."},
                code=404,
                request_id=request_id,
            )
        try:
            request.env["hader.mobile.subscription"].verify_company_subscription(
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
            data=sub.tenant_dto(),
            request_id=request_id,
        )

    @http.route(
        api_routes("/license/sync"),
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def sync_license(self, **_kwargs):
        """Endpoint called by Hader Central SaaS Server (hader_saas_manager) to push subscription updates to client servers."""
        request_id = self._request_id()
        expected_secret = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("hader_mobile.master_secret", DEFAULT_MASTER_SECRET)
        )
        supplied_secret = request.httprequest.headers.get("X-Hader-Master-Secret", "")
        if not supplied_secret or supplied_secret != expected_secret:
            return self._response(
                status="error",
                error={"code": "unauthorized_master_sync", "message": "Invalid master secret."},
                code=403,
                request_id=request_id,
            )
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            company_code = str(payload.get("company_code") or "").strip().upper()
            if not company_code:
                raise ValueError("company_code is required")
            Sub = request.env["hader.mobile.subscription"].sudo().with_context(skip_remote_sync=True)
            sub = Sub.search([("company_code", "=", company_code)], limit=1)
            default_company = request.env["res.company"].sudo().search([], order="id asc", limit=1)
            vals = {
                "company_code": company_code,
                "name": payload.get("name") or company_code,
                "name_en": payload.get("name_en") or payload.get("name") or company_code,
                "hosting_type": payload.get("hosting_type") or "external_odoo",
                "odoo_version": payload.get("odoo_version") or "18.0",
                "server_url": payload.get("server_url") or "https://odoo-test.ezdharpos.com",
                "db_name": payload.get("db_name") or False,
                "plan_type": payload.get("plan_type") or "pro",
                "state": payload.get("state") or "active",
                "max_employees": int(payload.get("max_employees") or 50),
                "feature_attendance": bool(payload.get("feature_attendance", True)),
                "feature_leaves": bool(payload.get("feature_leaves", True)),
                "feature_expenses": bool(payload.get("feature_expenses", True)),
                "feature_services": bool(payload.get("feature_services", True)),
                "feature_payroll": bool(payload.get("feature_payroll", True)),
                "feature_notifications": bool(payload.get("feature_notifications", True)),
                "last_sync_at": fields.Datetime.now(),
            }
            if payload.get("start_date"):
                vals["start_date"] = payload["start_date"]
            if payload.get("end_date"):
                vals["end_date"] = payload["end_date"]
            if payload.get("license_key"):
                vals["license_key"] = payload["license_key"]
            if payload.get("logo_base64"):
                vals["logo"] = payload["logo_base64"]
            if sub:
                sub.write(vals)
            else:
                if default_company:
                    vals["company_id"] = default_company.id
                sub = Sub.create(vals)
            sub.apply_features_to_local_flags()
            target_company = sub.company_id or default_company
            if vals.get("hosting_type") == "external_odoo" and target_company:
                # On an external client server, remove any stale subscription rows for the same company
                Sub.search([
                    ("company_id", "=", target_company.id),
                    ("id", "!=", sub.id),
                ]).unlink()
            if sub.state in ("suspended", "expired") and target_company:
                # Immediately revoke all active mobile sessions for this company when suspended/expired
                request.env["hader.mobile.session"].sudo().search([
                    ("company_id", "=", target_company.id),
                    ("revoked_at", "=", False),
                ]).write({"revoked_at": fields.Datetime.now()})
            active_count = request.env["hader.mobile.identity"].sudo().search_count([
                ("company_id", "=", target_company.id),
                ("active", "=", True),
                ("state", "!=", "revoked"),
            ]) if target_company else 0
            return self._response(
                data={
                    "company_code": sub.company_code,
                    "state": sub.state,
                    "max_employees": sub.max_employees,
                    "active_employees_count": active_count,
                    "synced_at": fields.Datetime.now().isoformat(),
                },
                request_id=request_id,
            )
        except Exception as exc:
            return self._response(
                status="error",
                error={"code": "sync_failed", "message": str(exc)},
                code=422,
                request_id=request_id,
            )

    @http.route(
        api_routes("/bootstrap"),
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
        sub = request.env["hader.mobile.subscription"].sudo().search(
            [("company_id", "=", session.identity_id.company_id.id)], order="id desc", limit=1
        )
        if not sub:
            sub = request.env["hader.mobile.subscription"].sudo().search([], order="id desc", limit=1)
        features = sub.features_dto() if sub else request.env["hader.mobile.feature"].bootstrap_dto()
        return self._response(
            data={
                "profile": session.identity_id.safe_profile_dto(),
                "features": features,
                "locale_defaults": {"primary": "ar", "supported": ["ar", "en"]},
                "routes": {"profile": API_PREFIX + "/me"},
            },
            request_id=request_id,
        )

    @http.route(
        api_routes("/me"),
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
        api_routes("/auth/enroll-face"),
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
            request.env["hader.mobile.audit"].sudo().create({
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
        api_routes("/auth/login"),
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
            .get_param("hader_mobile.auth_provider", "disabled")
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
            identity = request.env["hader.mobile.identity"].authenticate_password(
                payload.get("login_identifier"), payload.get("password")
            )
            # Single-device binding enforcement: an employee may only bind one active phone.
            device_name = (payload.get("device_name") or "Mobile device")[:128]
            hardware_bound = bool(payload.get("hardware_bound"))
            active_bound_devices = request.env["hader.mobile.device"].sudo().search([
                ("identity_id", "=", identity.id),
                ("revoked_at", "=", False),
                ("trusted", "=", True),
            ])
            if active_bound_devices and any(
                d.installation_id != installation_id for d in active_bound_devices
            ):
                # Automatic one-time migration from legacy random UUID ("Hader Android")
                # to persistent hardware UUID on the employee's existing phone.
                existing_owner = request.env["hader.mobile.device"].sudo().search(
                    [("installation_id", "=", installation_id)], limit=1
                )
                is_legacy_binding = all(
                    d.name in ("Hader Android", "Hader iOS", "Mobile device")
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
            device = request.env["hader.mobile.device"].sudo().search(
                [("installation_id", "=", installation_id)], limit=1
            )
            if device and (device.identity_id != identity or device.revoked_at):
                raise AccessDenied()
            if not device:
                device = request.env["hader.mobile.device"].sudo().create(
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
                if device_name not in ("Hader Android", "Hader iOS", "Mobile device"):
                    update_vals["name"] = device_name
                device.sudo().write(update_vals)
            now = fields.Datetime.now()
            # Revoke previous active sessions for this identity so only one session is active
            request.env["hader.mobile.session"].sudo().search([
                ("identity_id", "=", identity.id),
                ("revoked_at", "=", False),
            ]).write({"revoked_at": now})
            _session, access_token, refresh_token = request.env[
                "hader.mobile.session"
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
        api_routes("/auth/activate"),
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
        api_routes("/auth/refresh"), type="http", auth="public", methods=["POST"], csrf=False, save_session=False,
    )
    def refresh(self, **_kwargs):
        request_id = self._request_id()
        try:
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
            now = fields.Datetime.now()
            session, access_token, refresh_token = request.env["hader.mobile.session"].rotate_refresh_token(
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
