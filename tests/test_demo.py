import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from ordering import Order, load_menus
from web import create_web_app

ROOT = Path(__file__).resolve().parents[1]


class BrowserDemoTests(unittest.TestCase):
    def setUp(self):
        self.menus = load_menus(ROOT / "menus.sample.json")
        self.app = create_web_app(self.menus)
        self.client = self.app.test_client()
        data = self.client.get("/api/session").get_json()
        self.headers = {"X-Demo-Token": data["token"]}

    def message(self, message):
        response = self.client.post("/api/message", json={"message": message}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_sample_order_and_confirmed_artifacts(self):
        with patch("web.interpret", side_effect=AssertionError("Rehearsal called Gemini")):
            data = self.message("Two chicken biryanis, one mild, and a penne Alfredo. Is delivery free?")
            self.assertEqual(data["totals"]["subtotal_cents"], 4497)
            self.assertIn("$5.04", data["transcript"][-1]["assistant"])
            self.assertEqual(data["cart"]["Indian"][0]["notes"], "mild")
            self.assertEqual(data["cart"]["Indian"][1]["notes"], "")
            data = self.message("Add chicken tacos")
            self.assertEqual(data["totals"]["subtotal_cents"], 5694)
            self.assertEqual(data["totals"]["total_cents"], 6164)
            self.assertEqual(data["totals"]["delivery_cents"], 0)
            self.assertEqual(self.message("checkout")["stage"], "name")
            self.assertEqual(self.message("Alex Morgan")["stage"], "address")
            data = self.message("123 Demo Lane, Sample City")
            self.assertEqual(data["stage"], "confirm")
            self.assertIn("No text will be sent", data["transcript"][-1]["assistant"])
            with tempfile.TemporaryDirectory() as folder:
                original_save = Order.save
                with patch.object(Order, "save", lambda order: original_save(order, Path(folder))):
                    data = self.message("yes")
                self.assertEqual(data["stage"], "confirmed")
                self.assertEqual(len(list((Path(folder) / data["order_id"]).iterdir())), 5)
            with patch.object(Order, "save", side_effect=AssertionError("Saved twice")):
                self.assertEqual(self.message("yes")["stage"], "confirmed")

    def test_cart_validation_removal_and_reset(self):
        def cart(data):
            return self.client.post("/api/cart", json=data, headers=self.headers)
        self.assertEqual(cart({"restaurant": "Indian", "name": "Not a dish"}).status_code, 400)
        response = cart({"restaurant": "Indian", "name": "Garlic Naan", "price": 0})
        self.assertEqual(response.get_json()["totals"]["subtotal_cents"], 399)
        cart({"restaurant": "Indian", "name": "Garlic Naan", "action": "remove"})
        self.assertEqual(self.client.get("/api/session").get_json()["cart"], {})
        self.assertEqual(self.message("checkout")["stage"], "cart")
        self.message("Add chicken tacos")
        self.message("checkout")
        self.assertEqual(cart({"restaurant": "Indian", "name": "Garlic Naan"}).status_code, 409)
        data = self.client.post("/api/reset", json={}, headers=self.headers).get_json()
        self.assertEqual(data["stage"], "cart")
        self.assertEqual(data["cart"], {})

    def test_session_isolation_and_request_protection(self):
        self.message("Add chicken tacos")
        other = self.app.test_client()
        self.assertEqual(other.get("/api/session").get_json()["cart"], {})
        self.assertEqual(self.client.post("/api/reset", json={}).status_code, 403)
        for payload in ({"message": []}, {"message": " "}, {"message": "x" * 1001}, []):
            self.assertEqual(self.client.post("/api/message", json=payload, headers=self.headers).status_code, 400)
        self.assertEqual(other.post("/api/reset", json={}, headers=self.headers).status_code, 403)

    def test_menu_questions_do_not_order(self):
        for message in ("What is on the menu?", "Do you have chicken biryani?", "What vegetarian options do you have?"):
            data = self.message(message)
            self.assertEqual(data["cart"], {})
        self.assertIn("Paneer Tikka", data["transcript"][-1]["assistant"])

    def test_live_mode_uses_interpreter(self):
        client = create_web_app(self.menus, live=True).test_client()
        data = client.get("/api/session").get_json()
        self.assertEqual(data["mode"], "Gemini live")
        with patch("web.interpret", return_value={"items": [], "menu_answer": "Live answer"}) as interpreter:
            response = client.post("/api/message", json={"message": "What is available?"}, headers={"X-Demo-Token": data["token"]})
        interpreter.assert_called_once()
        self.assertIn("Live answer", response.get_json()["transcript"][-1]["assistant"])

    def test_delivery_threshold(self):
        order = Order(self.menus)
        order.cart = {"test": [{"quantity": 1, "unit_price_cents": 5000}]}
        self.assertEqual(order.totals()["delivery_cents"], 499)
        order.cart["test"][0]["unit_price_cents"] = 5001
        self.assertEqual(order.totals()["delivery_cents"], 0)

    def test_page_and_assets(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"One <em>conversation", response.data)
        for asset in ("app.js", "style.css", "favicon.svg"):
            with self.client.get("/static/" + asset) as asset_response:
                self.assertEqual(asset_response.status_code, 200)

    def test_voice_rejects_unsigned_calls(self):
        settings = {"PUBLIC_BASE_URL": "https://demo.example", "TWILIO_AUTH_TOKEN": "test-token", "DEMO_SMS_TO": "+14695550123", "TWILIO_TRIAL_WEBHOOK_KEY": ""}
        with patch.dict(os.environ, settings):
            phone = create_app(self.menus).test_client()
            self.assertEqual(phone.post("/voice", data={"From": settings["DEMO_SMS_TO"], "CallSid": "CA" + "a" * 32}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
