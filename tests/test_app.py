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
        response = self.client.post("/cart/add/1", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Gujarati Thali", response.data)
        response = self.client.post("/cart/update", data={"1": "3"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"447", response.data)

    def test_invalid_menu_item_returns_404(self):
        response = self.client.post("/cart/add/999")
        self.assertEqual(response.status_code, 404)

    def test_checkout_persists_order_and_clears_cart(self):
        self.client.post("/cart/add/1")
        response = self.client.post("/checkout", data={
            "customer": "Test Customer",
            "phone": "9999999999",
            "address": "Test address, Vadodara",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ORDER CONFIRMED", response.data)
        with homeeats.db() as conn:
            order = conn.execute("SELECT customer, total FROM orders").fetchone()
        self.assertEqual(order["customer"], "Test Customer")
        self.assertEqual(order["total"], 149)
        self.assertEqual(self.client.get("/cart").status_code, 200)
        self.assertIn(b"Your cart is waiting", self.client.get("/cart").data)

    def test_empty_cart_cannot_checkout(self):
        response = self.client.get("/checkout", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Explore the", response.data)

    def test_admin_is_disabled_without_password(self):
        with homeeats.app.test_request_context():
            homeeats.app.config["TESTING"] = True
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
