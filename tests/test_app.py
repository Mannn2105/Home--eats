import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app as homeeats


class HomeEatsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        homeeats.DB_PATH = Path(self.temp_dir.name) / "test.db"
        homeeats.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        homeeats.init_db()
        self.client = homeeats.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()
        os.environ.pop("RAZORPAY_KEY_ID", None)
        os.environ.pop("RAZORPAY_KEY_SECRET", None)

    def csrf(self, path):
        response = self.client.get(path)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match, f"CSRF token missing from {path}")
        return match.group(1).decode()

    def add_thali(self):
        token = self.csrf("/menu")
        response = self.client.post("/cart/add/1", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def submit_checkout(self, payment_method="cod"):
        token = self.csrf("/checkout")
        return self.client.post("/checkout", data={
            "csrf_token": token,
            "customer": "Test Customer",
            "phone": "9999999999",
            "address": "Test address, Vadodara",
            "payment_method": payment_method,
        }, follow_redirects=True)

    def test_home_page_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Good food feels", response.data)

    def test_menu_search_and_category_filter(self):
        response = self.client.get("/menu?category=Drinks&q=lassi")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mango Lassi", response.data)
        self.assertNotIn(b"Paneer Wrap", response.data)

    def test_add_to_cart_and_update_quantity(self):
        token = self.csrf("/menu")
        response = self.client.post("/cart/add/1", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Gujarati Thali", response.data)
        token = self.csrf("/cart")
        response = self.client.post("/cart/update", data={"1": "3", "csrf_token": token}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"447", response.data)

    def test_invalid_menu_item_returns_404(self):
        token = self.csrf("/menu")
        response = self.client.post("/cart/add/999", data={"csrf_token": token})
        self.assertEqual(response.status_code, 404)

    def test_razorpay_checkout_creates_pending_gateway_order(self):
        self.add_thali()
        os.environ["RAZORPAY_KEY_ID"] = "rzp_test_example"
        os.environ["RAZORPAY_KEY_SECRET"] = "test-secret"
        gateway = Mock()
        gateway.order.create.return_value = {"id": "order_test_123"}
        with patch.object(homeeats.razorpay, "Client", return_value=gateway):
            response = self.submit_checkout("razorpay")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"checkout.razorpay.com/v1/checkout.js", response.data)
        self.assertIn(b"order_test_123", response.data)
        with homeeats.db() as conn:
            order = conn.execute("SELECT * FROM orders").fetchone()
        self.assertEqual(order["payment_status"], "Payment pending")
        self.assertEqual(order["gateway_order_id"], "order_test_123")
        self.assertEqual(order["total"], 149)
        self.assertEqual(json.loads(order["items_json"])[0]["name"], "Gujarati Thali")

    def test_razorpay_payment_is_signature_and_capture_verified(self):
        self.add_thali()
        os.environ["RAZORPAY_KEY_ID"] = "rzp_test_example"
        os.environ["RAZORPAY_KEY_SECRET"] = "test-secret"
        gateway = Mock()
        gateway.order.create.return_value = {"id": "order_test_123"}
        gateway.payment.fetch.return_value = {
            "id": "pay_test_123", "order_id": "order_test_123",
            "amount": 14900, "currency": "INR", "status": "captured",
        }
        with patch.object(homeeats.razorpay, "Client", return_value=gateway):
            self.submit_checkout("razorpay")
            token = self.csrf("/checkout")
            response = self.client.post("/payment/verify", data={
                "csrf_token": token,
                "razorpay_order_id": "order_test_123",
                "razorpay_payment_id": "pay_test_123",
                "razorpay_signature": "valid-test-signature",
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PAYMENT CONFIRMED", response.data)
        self.assertIn(b"Payment was processed and verified", response.data)
        with homeeats.db() as conn:
            order = conn.execute("SELECT * FROM orders").fetchone()
        self.assertEqual(order["payment_status"], "Paid")
        self.assertEqual(order["gateway_payment_id"], "pay_test_123")
        gateway.utility.verify_payment_signature.assert_called_once()

    def test_razorpay_unavailable_without_credentials(self):
        self.add_thali()
        response = self.submit_checkout("razorpay")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Online payments are temporarily unavailable", response.data)
        with homeeats.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)

    def test_cash_on_delivery_is_pending(self):
        self.add_thali()
        response = self.submit_checkout("cod")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cash on Delivery", response.data)
        self.assertIn(b"Payment due on delivery", response.data)
        self.assertIn(b"COD-", response.data)

    def test_receipt_link_is_protected_by_random_token(self):
        self.add_thali()
        self.submit_checkout("cod")
        with homeeats.db() as conn:
            order = conn.execute("SELECT id, receipt_token FROM orders").fetchone()
        bad = self.client.get(f"/receipt/{order['id']}/wrong-token")
        good = self.client.get(f"/receipt/{order['id']}/{order['receipt_token']}")
        self.assertEqual(bad.status_code, 404)
        self.assertEqual(good.status_code, 200)

    def test_checkout_rejects_invalid_phone(self):
        self.add_thali()
        token = self.csrf("/checkout")
        response = self.client.post("/checkout", data={
            "csrf_token": token,
            "customer": "Test Customer",
            "phone": "not-a-phone",
            "address": "Test address",
            "payment_method": "cod",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"valid phone number", response.data)
        with homeeats.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)

    def test_invalid_payment_method_is_rejected(self):
        self.add_thali()
        token = self.csrf("/checkout")
        response = self.client.post("/checkout", data={
            "csrf_token": token, "customer": "Test Customer",
            "phone": "9999999999", "address": "Some address",
            "payment_method": "bitcoin",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Choose Razorpay or Cash on Delivery", response.data)
        with homeeats.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)

    def test_missing_csrf_token_is_rejected(self):
        response = self.client.post("/cart/add/1")
        self.assertEqual(response.status_code, 400)

    def test_empty_cart_cannot_checkout(self):
        response = self.client.get("/checkout", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Explore the", response.data)

    def test_admin_is_disabled_without_password(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
