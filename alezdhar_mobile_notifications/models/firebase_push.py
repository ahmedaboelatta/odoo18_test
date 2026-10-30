import os

from odoo import _, api, fields, models


class AlezdharMobilePushDelivery(models.Model):
    _name = "alezdhar.mobile.push.delivery"
    _description = "Mobile Push Delivery"
    _order = "create_date desc, id desc"

    inbox_id = fields.Many2one(
        "alezdhar.mobile.notification.inbox", required=True, index=True, ondelete="cascade"
    )
    device_id = fields.Many2one(
        "alezdhar.mobile.device", required=True, index=True, ondelete="cascade"
    )
    employee_id = fields.Many2one(related="inbox_id.employee_id", store=True, index=True)
    state = fields.Selection(
        [("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed"),
         ("unregistered", "Unregistered")],
        default="pending", required=True, index=True,
    )
    firebase_message_id = fields.Char(readonly=True)
    error_code = fields.Char(readonly=True)
    error_message = fields.Text(readonly=True)
    sent_at = fields.Datetime(readonly=True)

    @api.model
    def _firebase_app(self):
        try:
            import firebase_admin
            from firebase_admin import credentials
        except ImportError as exc:
            raise RuntimeError("firebase-admin is not installed on the Odoo server") from exc

        try:
            return firebase_admin.get_app("alezdhar")
        except ValueError:
            path = (
                self.env["ir.config_parameter"].sudo().get_param(
                    "alezdhar_mobile.firebase_credentials_path",
                    "/etc/odoo/secrets/alezdhar-firebase-service-account.json",
                )
            )
            if not path or not os.path.isfile(path):
                raise RuntimeError("Firebase service account file is not available")
            return firebase_admin.initialize_app(
                credentials.Certificate(path), name="alezdhar"
            )

    @api.model
    def send_inbox(self, inbox):
        devices = self.env["alezdhar.mobile.device"].sudo().search([
            ("identity_id", "=", inbox.identity_id.id),
            ("push_enabled", "=", True),
            ("push_installation_id", "!=", False),
            ("revoked_at", "=", False),
        ])
        deliveries = self.create([{
            "inbox_id": inbox.id, "device_id": device.id,
        } for device in devices]) if devices else self.browse()
        if not deliveries:
            return deliveries

        try:
            app = self._firebase_app()
            from firebase_admin import messaging
        except Exception as exc:  # configuration/dependency failure is recorded per target
            deliveries.write({"state": "failed", "error_code": "configuration_error",
                              "error_message": str(exc)[:1000]})
            return deliveries

        for delivery in deliveries:
            try:
                title, body = inbox._localized_content(delivery.device_id.push_locale or "ar")
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                        image=inbox.image_url or None,
                    ),
                    data={
                        "notification_id": str(inbox.id),
                        "category": inbox.category,
                        "correction_ref": str(inbox.correction_id.id or ""),
                        "route": "requests" if inbox.correction_id or inbox.category.startswith("leave_") else "notifications",
                    },
                    android=messaging.AndroidConfig(
                        priority="high",
                        notification=messaging.AndroidNotification(
                            channel_id="alezdhar_general",
                            sound="default",
                        ),
                    ),
                    fid=delivery.device_id.push_installation_id,
                )
                message_id = messaging.send(message, app=app)
                delivery.write({"state": "sent", "firebase_message_id": message_id,
                                "sent_at": fields.Datetime.now()})
            except messaging.UnregisteredError as exc:
                delivery.device_id.sudo().write({"push_enabled": False})
                delivery.write({"state": "unregistered", "error_code": "unregistered",
                                "error_message": str(exc)[:1000]})
            except Exception as exc:  # Firebase errors must not roll back the inbox record
                delivery.write({"state": "failed", "error_code": exc.__class__.__name__,
                                "error_message": str(exc)[:1000]})
        return deliveries
