import hmac
import json
import logging

from odoo import SUPERUSER_ID, fields, http
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
        # auth='none' has no authenticated uid.  sudo() only enables superuser
        # mode and can still leave env.user empty in Odoo 18, which breaks
        # defaults used while creating a real sale order.  Run the complete
        # webhook transaction with an explicit internal user instead.
        config_model = request.env['techrar.config'].with_user(SUPERUSER_ID)
        configs = config_model.search([
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

        wizard_model = request.env['techrar.sync.wizard'].with_user(SUPERUSER_ID)
        try:
            is_test_event = (
                payload.get('event') == 'test'
                or payload.get('test') is not None
                or (
                    isinstance(payload.get('data'), dict)
                    and payload['data'].get('event') == 'test'
                )
            )
            if is_test_event:
                result = 'test_received'
                techrar_order_id = ''
            else:
                order_data = wizard_model._extract_webhook_order(payload)
                techrar_order_id = wizard_model._extract_webhook_order_id(
                    payload, order_data,
                )
                if not techrar_order_id:
                    raise ValueError('Techrar webhook payload does not contain an order ID.')

                # Techrar gives the endpoint only 10 seconds to respond.  A
                # real order can require an API lookup plus sale, invoice and
                # payment creation, so acknowledge receipt immediately and
                # trigger the safe one-day sync in the background.  The sync
                # is idempotent by Techrar order ID and processes newest
                # orders first.
                cron = request.env.ref(
                    'techrar_connector.ir_cron_techrar_sync_orders',
                    raise_if_not_found=False,
                )
                if not cron:
                    raise ValueError('Techrar synchronization job is not installed.')
                cron.with_user(SUPERUSER_ID)._trigger()
                result = 'queued'
            config.write({
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
            config.write({
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
