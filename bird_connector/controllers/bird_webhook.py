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
    def _verify_signature(raw_body, request_urls, timestamp, signature, signing_key):
        """Validate a Bird Notifications webhook signature.

        Bird signs: timestamp + \"\n\" + request URL + \"\n\" +
        SHA256(raw body) as *binary bytes*, then HMAC-SHA256 with the
        subscription signing key. ``messagebird-signature`` is Base64.

        ``request_urls`` accepts more than one canonical candidate because Odoo
        is commonly deployed behind a reverse proxy. The public URL configured
        on the Bird organization is tried first by the caller.
        """
        if not all([timestamp, signature, signing_key]):
            return False
        try:
            received = base64.b64decode(signature, validate=True)
            body_checksum = hashlib.sha256(raw_body).digest()
            if isinstance(request_urls, str):
                request_urls = [request_urls]

            seen = set()
            for request_url in request_urls or []:
                request_url = str(request_url or '').strip()
                if not request_url or request_url in seen:
                    continue
                seen.add(request_url)
                payload = (
                    str(timestamp).encode('utf-8')
                    + b'\n'
                    + request_url.encode('utf-8')
                    + b'\n'
                    + body_checksum
                )
                calculated = hmac.new(
                    signing_key.encode('utf-8'),
                    payload,
                    hashlib.sha256,
                ).digest()
                if hmac.compare_digest(received, calculated):
                    return True
            return False
        except Exception:
            _logger.exception('Unable to validate Bird webhook signature')
            return False

    @http.route('/bird/webhook/<int:organization_id>/<string:token>', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def bird_webhook(self, organization_id, token, **kwargs):
        # Webhook callbacks must stay independent from mail/chatter side effects.
        # An unrelated custom module can temporarily leave a mail.thread-related
        # model/schema inconsistent during an upgrade.  Disabling tracking for
        # this stateless integration request prevents chatter pre-commit hooks
        # from turning a valid Bird callback into HTTP 500.
        webhook_ctx = dict(
            request.env.context,
            tracking_disable=True,
            mail_notrack=True,
            mail_create_nolog=True,
        )
        org = request.env['bird.organization'].with_context(webhook_ctx).sudo().browse(organization_id)
        if not org.exists() or not org.webhook_token or not hmac.compare_digest(org.webhook_token, token):
            return request.make_response('Not Found', status=404)

        raw_body = request.httprequest.get_data(cache=True) or b''
        try:
            data = json.loads(raw_body.decode('utf-8') or '{}')
        except Exception:
            return request.make_response('Invalid JSON', status=400)

        event_name = data.get('event') or ''
        channel_external_id = request.env['bird.webhook.event'].sudo()._deep_find(data, ('channelId', 'channel_id'))
        Subscription = request.env['bird.webhook.subscription'].with_context(webhook_ctx).sudo()
        subscription = Subscription.search([
            ('organization_id', '=', org.id),
            ('event', '=', event_name),
            ('managed_by_connector', '=', True),
            '|', ('channel_id.channel_id', '=', str(channel_external_id or '')), ('channel_id', '=', False),
        ], limit=1)
        # Portable/recovered deployments can receive a valid Bird callback from a
        # subscription that was synchronized as External rather than created by this
        # database.  Do not throw away the channel context in that case.
        if not subscription:
            subscription = Subscription.search([
                ('organization_id', '=', org.id),
                ('event', '=', event_name),
                '|', ('channel_id.channel_id', '=', str(channel_external_id or '')), ('channel_id', '=', False),
            ], order='managed_by_connector desc, id desc', limit=1)

        signing_key = subscription.signing_key if subscription else org.webhook_signing_key
        signature = request.httprequest.headers.get('messagebird-signature')
        timestamp = request.httprequest.headers.get('messagebird-request-timestamp')

        # Bird signs the *public* webhook URL. request.httprequest.url may show
        # http:// when Odoo runs behind Nginx without proxy_mode, so always try
        # the exact URL that was registered with Bird first.
        public_url = (subscription.webhook_url if subscription else False) or org.webhook_public_url
        forwarded_proto = request.httprequest.headers.get('X-Forwarded-Proto')
        forwarded_host = request.httprequest.headers.get('X-Forwarded-Host') or request.httprequest.headers.get('Host')
        forwarded_url = False
        if forwarded_proto and forwarded_host:
            forwarded_url = '%s://%s%s' % (
                forwarded_proto.split(',')[0].strip(),
                forwarded_host.split(',')[0].strip(),
                request.httprequest.full_path.rstrip('?'),
            )
        signature_valid = self._verify_signature(
            raw_body,
            [public_url, forwarded_url, request.httprequest.url],
            timestamp,
            signature,
            signing_key,
        )

        if org.webhook_verify_signatures and not signature_valid:
            _logger.warning('Rejected Bird webhook for organization %s: invalid signature', org.id)
            return request.make_response('Invalid signature', status=401)

        event = request.env['bird.webhook.event'].with_context(webhook_ctx).sudo().create({
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
