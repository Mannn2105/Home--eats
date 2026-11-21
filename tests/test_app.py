import json
import re
import tempfile
import unittest
from pathlib import Path

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

    def csrf(self, path):
        response = self.client.get(path)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match, f"CSRF token missing from {path}")
        return match.group(1).decode()

    def add_thali(self):
        token = self.csrf("/menu")
        response = self.client.post("/cart/add/1", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def submit_checkout(self, payment_method="upi_demo"):
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

    def test_demo_upi_payment_creates_receipt(self):
        self.add_thali()
        response = self.submit_checkout("upi_demo")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PAYMENT RECEIPT", response.data)
        self.assertIn(b"UPI (Demo)", response.data)
        self.assertIn(b"Demo payment successful", response.data)
        self.assertIn(b"DEMO-UPI-", response.data)
        self.assertIn(b"Gujarati Thali", response.data)
        with homeeats.db() as conn:
            order = conn.execute("SELECT * FROM orders").fetchone()
        self.assertEqual(order["total"], 149)
        self.assertEqual(order["payment_method"], "UPI (Demo)")
        self.assertTrue(order["receipt_token"])
        self.assertEqual(json.loads(order["items_json"])[0]["name"], "Gujarati Thali")

    def test_demo_card_payment_is_labelled_as_simulated(self):
        self.add_thali()
        response = self.submit_checkout("card_demo")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Card (Demo)", response.data)
        self.assertIn(b"DEMO-CARD-", response.data)
        self.assertIn(b"no money moved", response.data)

    def test_cash_on_delivery_is_pending(self):
        self.add_thali()
        response = self.submit_checkout("cod")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cash on Delivery", response.data)
        self.assertIn(b"Payment due on delivery", response.data)
        self.assertIn(b"COD-", response.data)

    def test_receipt_link_is_protected_by_random_token(self):
        self.add_thali()
        self.submit_checkout("upi_demo")
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
            "payment_method": "upi_demo",
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
        self.assertIn(b"Choose one of the available", response.data)
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
