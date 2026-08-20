import base64
import mimetypes
import secrets
from urllib.parse import urlparse

import requests

from odoo import http
from odoo.http import request


class BirdMediaController(http.Controller):
    @http.route(
        "/bird_connector/template_media/<int:template_id>/<string:token>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        sitemap=False,
    )
    def bird_template_media(self, template_id, token, **kwargs):
        template = request.env["bird.template"].sudo().browse(template_id).exists()
        if not template or not template.header_image or not template.header_media_token:
            return request.not_found()

        if not secrets.compare_digest(str(template.header_media_token), str(token)):
            return request.not_found()

        try:
            payload = base64.b64decode(template.header_image)
        except Exception:
            return request.not_found()

        filename = template.header_image_filename or f"bird-template-{template.id}.jpg"
        mimetype = mimetypes.guess_type(filename)[0] or "image/jpeg"
        headers = [
            ("Content-Type", mimetype),
            ("Content-Length", str(len(payload))),
            ("Cache-Control", "public, max-age=3600"),
            ("Content-Disposition", f'inline; filename="{filename}"'),
        ]
        return request.make_response(payload, headers=headers)

    @staticmethod
    def _is_allowed_bird_media_url(url):
        """Only proxy HTTPS media URLs controlled by Bird.

        Incoming Channels messages expose a mediaUrl on Bird's media service.
        Keeping this allow-list prevents the Odoo endpoint from becoming a
        general-purpose authenticated SSRF proxy.
        """
        try:
            parsed = urlparse(url or "")
        except Exception:
            return False
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        host = parsed.hostname.lower().rstrip(".")
        return (
            host == "api.bird.com"
            or host == "media.api.bird.com"
            or host.endswith(".bird.com")
            or host == "api.bird.one"
            or host.endswith(".bird.one")
        )

    @http.route(
        "/bird_connector/conversation_media/<int:message_id>",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        sitemap=False,
    )
    def bird_conversation_media(self, message_id, download=False, **kwargs):
        """Fetch protected incoming Bird media server-side.

        Bird incoming message mediaUrl endpoints require the Bird AccessKey.
        Browser <img>/<video> requests cannot safely include that secret, so
        authenticated Odoo users load media through this endpoint instead.
        """
        message = request.env["bird.conversation.message"].sudo().browse(message_id).exists()
        if not message or not message.media_url:
            return request.not_found()

        source_url = message.media_url.strip()
        if not self._is_allowed_bird_media_url(source_url):
            return request.not_found()

        organization = message.conversation_id.organization_id
        access_key = organization.access_key if organization else False
        if not access_key:
            return request.make_response("Bird access key is not configured.", status=503)

        timeout = max(int(getattr(organization, "request_timeout", 20) or 20), 1)
        try:
            response = requests.get(
                source_url,
                headers={
                    "Authorization": f"AccessKey {access_key}",
                    "Accept": "*/*",
                },
                timeout=timeout,
                stream=True,
                allow_redirects=True,
            )
        except requests.RequestException:
            return request.make_response("Unable to retrieve Bird media.", status=502)

        if not (200 <= response.status_code < 300):
            response.close()
            return request.make_response(
                f"Bird media request failed (HTTP {response.status_code}).",
                status=502,
            )

        # Avoid buffering arbitrarily large responses in an Odoo worker.
        max_bytes = 32 * 1024 * 1024
        chunks = []
        total = 0
        try:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    response.close()
                    return request.make_response("Bird media is too large to preview.", status=413)
                chunks.append(chunk)
        finally:
            response.close()
        payload = b"".join(chunks)

        content_type = (
            response.headers.get("Content-Type")
            or message.media_mime_type
            or mimetypes.guess_type(message.media_name or "")[0]
            or "application/octet-stream"
        )
        filename = (message.media_name or f"bird-media-{message.id}").replace('"', "")
        disposition = "attachment" if str(download).lower() in ("1", "true", "yes") else "inline"
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(payload))),
            ("Cache-Control", "private, max-age=300"),
            ("Content-Disposition", f'{disposition}; filename="{filename}"'),
        ]
        return request.make_response(payload, headers=headers)
