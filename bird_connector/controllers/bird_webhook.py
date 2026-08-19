import base64
import hashlib
import hmac
import json
import logging

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class BirdWebhookController(http.Controller):

    @staticmethod
    def _verify_signature(raw_body, request_url, timestamp, signature, signing_key):
        if not all([timestamp, signature, signing_key]):
            return False
        try:
            received = base64.b64decode(signature)
            body_checksum = hashlib.sha256(raw_body).hexdigest()
            payload = f'{timestamp}{request_url}{body_checksum}'
            calculated = hmac.new(
                signing_key.encode('latin-1'),
                payload.encode('latin-1'),
                hashlib.sha256,
            ).digest()
            return hmac.compare_digest(received, calculated)
        except Exception:
            return False

    @http.route('/bird/webhook/<int:organization_id>/<string:token>', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def bird_webhook(self, organization_id, token, **kwargs):
        org = request.env['bird.organization'].sudo().browse(organization_id)
        if not org.exists() or not org.webhook_token or not hmac.compare_digest(org.webhook_token, token):
            return request.make_response('Not Found', status=404)

        raw_body = request.httprequest.get_data(cache=True) or b''
        try:
            data = json.loads(raw_body.decode('utf-8') or '{}')
        except Exception:
            return request.make_response('Invalid JSON', status=400)

        event_name = data.get('event') or ''
        channel_external_id = request.env['bird.webhook.event'].sudo()._deep_find(data, ('channelId', 'channel_id'))
        subscription = request.env['bird.webhook.subscription'].sudo().search([
            ('organization_id', '=', org.id),
            ('event', '=', event_name),
            '|', ('channel_id.channel_id', '=', str(channel_external_id or '')), ('channel_id', '=', False),
        ], limit=1)

        signing_key = subscription.signing_key if subscription else org.webhook_signing_key
        signature = request.httprequest.headers.get('messagebird-signature')
        timestamp = request.httprequest.headers.get('messagebird-request-timestamp')
        signature_valid = self._verify_signature(raw_body, request.httprequest.url, timestamp, signature, signing_key)

        if org.webhook_verify_signatures and not signature_valid:
            _logger.warning('Rejected Bird webhook for organization %s: invalid signature', org.id)
            return request.make_response('Invalid signature', status=401)

        event = request.env['bird.webhook.event'].sudo().create({
            'organization_id': org.id,
            'subscription_id': subscription.id if subscription else False,
            'workspace_external_id': org.workspace_id,
            'channel_external_id': str(channel_external_id or ''),
            'event': event_name,
            'signature_valid': signature_valid,
            'payload': json.dumps(data, indent=2, ensure_ascii=False, default=str),
            'received_at': fields.Datetime.now(),
        })
        if subscription:
            subscription.sudo().write({
                'last_event_at': fields.Datetime.now(),
                'event_count': subscription.event_count + 1,
            })
        event._process_event(data)
        return request.make_response('OK', status=200, headers=[('Content-Type', 'text/plain')])
