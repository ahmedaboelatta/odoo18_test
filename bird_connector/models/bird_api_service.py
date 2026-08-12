import json
import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)


class BirdApiService(models.AbstractModel):
    _name = "bird.api.service"
    _description = "Bird API Service"

    _base_url = "https://api.bird.com"

    @api.model
    def _headers(self, access_key):
        return {
            "Authorization": f"AccessKey {access_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @api.model
    def _safe_json(self, response):
        try:
            return response.json()
        except Exception:
            return {"raw": response.text or ""}

    @api.model
    def request(self, method, path, access_key, payload=None, params=None, timeout=30):
        """Execute one Bird API request and always return a structured result.

        HTTP failures and network failures are returned rather than raised so calling
        models can create/preserve audit logs inside the same Odoo transaction.
        """
        if not access_key:
            return {
                "ok": False,
                "status_code": 0,
                "data": {},
                "error": "Missing Bird API access key.",
            }

        url = path if path.startswith("http") else f"{self._base_url}{path}"

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=self._headers(access_key),
                json=payload,
                params=params,
                timeout=timeout,
            )
            data = self._safe_json(response)
            ok = 200 <= response.status_code < 300
            result = {
                "ok": ok,
                "status_code": response.status_code,
                "data": data,
                "error": False,
            }
            if not ok:
                error = ""
                if isinstance(data, dict):
                    error = (
                        data.get("message")
                        or data.get("error")
                        or data.get("detail")
                        or data.get("title")
                        or ""
                    )
                result["error"] = error or response.text or f"HTTP {response.status_code}"
                _logger.error(
                    "Bird API %s %s failed: HTTP %s - %s",
                    method.upper(),
                    url,
                    response.status_code,
                    result["error"],
                )
            return result
        except requests.RequestException as exc:
            _logger.exception("Bird API network error on %s %s", method.upper(), url)
            return {
                "ok": False,
                "status_code": 0,
                "data": {},
                "error": str(exc),
            }
        except Exception as exc:
            _logger.exception("Unexpected Bird API error on %s %s", method.upper(), url)
            return {
                "ok": False,
                "status_code": 0,
                "data": {},
                "error": str(exc),
            }

    @api.model
    def get(self, path, access_key, params=None, timeout=30):
        return self.request("GET", path, access_key, params=params, timeout=timeout)

    @api.model
    def post(self, path, access_key, payload=None, timeout=30):
        return self.request("POST", path, access_key, payload=payload, timeout=timeout)

    @api.model
    def patch(self, path, access_key, payload=None, timeout=30):
        return self.request("PATCH", path, access_key, payload=payload, timeout=timeout)

    @api.model
    def delete(self, path, access_key, payload=None, timeout=30):
        return self.request("DELETE", path, access_key, payload=payload, timeout=timeout)

    @api.model
    def pretty_json(self, value):
        try:
            return json.dumps(value or {}, indent=2, ensure_ascii=False, default=str)
        except Exception:
            return str(value or "")
