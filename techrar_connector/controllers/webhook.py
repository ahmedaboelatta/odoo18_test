import hmac
import json
import logging

from odoo import fields, http
from odoo.http import request
from werkzeug.wrappers import Response


_logger = logging.getLogger(__name__)


class TechrarWebhookController(http.Controller):

    @http.route(
        '/techrar/webhook/order-completed',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def techrar_order_completed(self, **kwargs):
        del kwargs
        supplied_token = request.httprequest.headers.get('X-Techrar-Odoo-Token', '')
        configs = request.env['techrar.config'].sudo().search([
            ('webhook_token', '!=', False),
        ])
        config = next((
            item for item in configs
            if hmac.compare_digest(item.webhook_token or '', supplied_token)
        ), False)
        if not config or not supplied_token:
            return self._json_response({'status': 'unauthorized'}, status=401)

        raw_body = request.httprequest.get_data(cache=False, as_text=True)
        try:
            payload = json.loads(raw_body or '{}')
        except (TypeError, ValueError):
            return self._json_response({'status': 'invalid_json'}, status=400)
        if not isinstance(payload, dict):
            return self._json_response({'status': 'invalid_payload'}, status=400)

        wizard = request.env['techrar.sync.wizard'].sudo().create({
            'config_id': config.id,
            'from_date': request.env['techrar.sync.wizard']._context_today(),
            'to_date': request.env['techrar.sync.wizard']._context_today(),
            'run_source': 'webhook',
        })
        try:
            with request.env.cr.savepoint():
                result, techrar_order_id = wizard._process_webhook_payload(payload, config)
            config.sudo().write({
                'webhook_last_received_at': fields.Datetime.now(),
                'webhook_last_status': 'success',
                'webhook_last_error': False,
            })
            return self._json_response({
                'status': 'ok',
                'result': result,
                'order_id': techrar_order_id,
            })
        except Exception as error:
            _logger.exception('Techrar webhook processing failed.')
            config.sudo().write({
                'webhook_last_received_at': fields.Datetime.now(),
                'webhook_last_status': 'failed',
                'webhook_last_error': str(error)[:1000],
            })
            return self._json_response({'status': 'processing_failed'}, status=500)

    @staticmethod
    def _json_response(payload, status=200):
        return Response(
            json.dumps(payload),
            status=status,
            content_type='application/json; charset=utf-8',
        )
