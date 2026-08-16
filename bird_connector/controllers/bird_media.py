import base64
import mimetypes
import secrets

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
