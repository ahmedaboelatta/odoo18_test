import json
from types import SimpleNamespace

from odoo.tests.common import TransactionCase


class TestAiForwardPayload(TransactionCase):
    def _message(self, body, kind="text", text="Hello"):
        channel = SimpleNamespace(name="ZED Meals", connected_account="+966500000000")
        contact = SimpleNamespace(whatsapp_number="+966511111111")
        return SimpleNamespace(
            bird_message_id="bird-in-1", message_type=kind, body=text,
            raw_payload=json.dumps({"body": body}), channel_id=channel,
            contact_id=contact, conversation_id=SimpleNamespace(id=42),
        )

    def test_text_payload_keeps_existing_fields(self):
        profile = self.env["ai.whatsapp.profile"].new({"name": "ZED Meals", "code": "zed_meals"})
        payload = profile._build_ai_forward_payload(self._message({"type": "text"}))
        self.assertEqual(payload["message_type"], "text")
        self.assertEqual(payload["text"], "Hello")
        self.assertEqual(payload["conversation_id"], "42")
        self.assertNotIn("location", payload)

    def test_location_payload_coordinates(self):
        profile = self.env["ai.whatsapp.profile"].new({"name": "ZED Meals", "code": "zed_meals"})
        body = {"type": "location", "location": {
            "coordinates": {"latitude": 21.43435, "longitude": 39.218643},
            "location": {"address": "", "label": ""},
        }}
        payload = profile._build_ai_forward_payload(self._message(body, kind="location", text="LOCATION"))
        self.assertEqual(payload["message_type"], "location")
        self.assertEqual(payload["customer_message"], "LOCATION")
        self.assertEqual(payload["latitude"], 21.43435)
        self.assertEqual(payload["longitude"], 39.218643)
        self.assertEqual(payload["location"]["coordinates"]["latitude"], 21.43435)
        self.assertEqual(payload["location"]["coordinates"]["longitude"], 39.218643)
        self.assertEqual(payload["location_address"], "")
        self.assertEqual(payload["location_label"], "")
        self.assertNotIn("secret", json.dumps(payload).lower())

    def test_unsupported_type_is_rejected_before_request(self):
        profile = self.env["ai.whatsapp.profile"].new({"name": "ZED Meals", "code": "zed_meals"})
        with self.assertRaisesRegex(ValueError, "Unsupported inbound message type"):
            profile._build_ai_forward_payload(self._message({"type": "image"}, kind="image"))

    def test_invalid_location_is_rejected_before_request(self):
        profile = self.env["ai.whatsapp.profile"].new({"name": "ZED Meals", "code": "zed_meals"})
        with self.assertRaisesRegex(ValueError, "coordinates"):
            profile._build_ai_forward_payload(self._message({"type": "location"}, kind="location"))
