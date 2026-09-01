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

                result = 'queued'
                event_model = request.env['techrar.webhook.event'].with_user(
                    SUPERUSER_ID,
                )
                queued_event = event_model.search([
                    ('config_id', '=', config.id),
                    ('techrar_order_id', '=', techrar_order_id),
                ], limit=1)
                if queued_event:
                    if queued_event.state != 'done':
                        queued_event.write({
                            'payload': payload,
                            'state': 'pending',
                            'last_error': False,
                        })
                    else:
                        result = 'already_processed'
                else:
                    queued_event = event_model.create({
                        'config_id': config.id,
                        'techrar_order_id': techrar_order_id,
                        'payload': payload,
                    })

                # Techrar gives the endpoint only 10 seconds to respond.
                # Acknowledge immediately, then let the dedicated queue create
                # the sale, invoice and payment outside this HTTP request.
                cron = request.env.ref(
                    'techrar_connector.ir_cron_techrar_process_webhooks',
                    raise_if_not_found=False,
                )
                if not cron:
                    raise ValueError('Techrar webhook queue job is not installed.')
                cron.with_user(SUPERUSER_ID)._trigger()
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
