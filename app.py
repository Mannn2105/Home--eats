import hmac
import json
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException
import razorpay

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "homeeats.db"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)

PAYMENT_METHODS = {
    "razorpay": "Razorpay (UPI / Cards / Netbanking)",
    "cod": "Cash on Delivery",
}

MENU = [
    {"id": 1, "name": "Gujarati Thali", "category": "Meals", "description": "Rotli, shaak, dal, rice and a little sweetness.", "price": 149, "emoji": "🍱", "tag": "Bestseller", "image_url": "https://images.unsplash.com/photo-1794468507547-1c193172d3c2?auto=format&fit=crop&w=900&q=85"},
    {"id": 2, "name": "Punjabi Chole Bowl", "category": "Meals", "description": "Slow-cooked chole with jeera rice and salad.", "price": 129, "emoji": "🥘", "tag": "Comfort food", "image_url": "https://images.unsplash.com/photo-1788601988466-9f361c34c6cb?auto=format&fit=crop&w=900&q=85"},
    {"id": 3, "name": "Paneer Wrap", "category": "Quick Bites", "description": "Spiced paneer, crunchy vegetables and mint chutney.", "price": 99, "emoji": "🌯", "tag": "Popular", "image_url": "https://images.unsplash.com/photo-1639744093483-86714cd62a3b?auto=format&fit=crop&w=900&q=85"},
    {"id": 4, "name": "Masala Khichdi", "category": "Meals", "description": "Homestyle moong dal khichdi with kadhi.", "price": 109, "emoji": "🍲", "tag": "Homestyle", "image_url": "https://images.unsplash.com/photo-1789994405563-b372d9a270c2?auto=format&fit=crop&w=900&q=85"},
    {"id": 5, "name": "Veg Sandwich", "category": "Quick Bites", "description": "Toasted sandwich with fresh vegetables and cheese.", "price": 79, "emoji": "🥪", "tag": "", "image_url": "https://images.unsplash.com/photo-1716535233357-822bcc293573?auto=format&fit=crop&w=900&q=85"},
    {"id": 6, "name": "Mango Lassi", "category": "Drinks", "description": "Chilled yoghurt drink blended with mango.", "price": 59, "emoji": "🥭", "tag": "", "image_url": "https://images.unsplash.com/photo-1697642452436-9c40773cbcbb?auto=format&fit=crop&w=900&q=85"},
    {"id": 7, "name": "Gulab Jamun", "category": "Desserts", "description": "Two soft, syrup-soaked festive favourites.", "price": 49, "emoji": "🍮", "tag": "", "image_url": "https://images.unsplash.com/photo-1593701461250-d7b22dfd3a77?auto=format&fit=crop&w=900&q=85"},
    {"id": 8, "name": "Masala Chaas", "category": "Drinks", "description": "Refreshing spiced buttermilk.", "price": 35, "emoji": "🥛", "tag": "Refreshing", "image_url": "https://images.unsplash.com/photo-1697642452436-9c40773cbcbb?auto=format&fit=crop&w=900&q=85"}
]


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables and safely add payment fields to existing installations."""
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            items TEXT NOT NULL,
            total REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payment_method TEXT NOT NULL DEFAULT 'Not recorded',
            payment_status TEXT NOT NULL DEFAULT 'Demo order',
            transaction_id TEXT,
            receipt_token TEXT,
            items_json TEXT NOT NULL DEFAULT '[]',
            gateway_order_id TEXT,
            gateway_payment_id TEXT
        )""")
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
        migrations = {
            "payment_method": "ALTER TABLE orders ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'Not recorded'",
            "payment_status": "ALTER TABLE orders ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'Demo order'",
            "transaction_id": "ALTER TABLE orders ADD COLUMN transaction_id TEXT",
            "receipt_token": "ALTER TABLE orders ADD COLUMN receipt_token TEXT",
            "items_json": "ALTER TABLE orders ADD COLUMN items_json TEXT NOT NULL DEFAULT '[]'",
            "gateway_order_id": "ALTER TABLE orders ADD COLUMN gateway_order_id TEXT",
            "gateway_payment_id": "ALTER TABLE orders ADD COLUMN gateway_payment_id TEXT",
        }
        for column, statement in migrations.items():
            if column not in existing:
                conn.execute(statement)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_receipt_token ON orders(receipt_token)")


@app.context_processor
def inject_csrf_token():
    def csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token
    return {"csrf_token": csrf_token}


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not expected or not submitted or not hmac.compare_digest(submitted, expected):
            abort(400, description="Invalid or missing security token. Refresh the page and try again.")


def cart_details():
    cart_data = session.get("cart", {})
    items, total = [], 0
    for item in MENU:
        try:
            qty = max(0, min(int(cart_data.get(str(item["id"]), 0)), 20))
        except (TypeError, ValueError):
            qty = 0
        if qty:
            line = {**item, "qty": qty, "subtotal": qty * item["price"]}
            items.append(line)
            total += line["subtotal"]
    return items, total


@app.route("/")
def home():
    return render_template("index.html", featured=MENU[:4])


@app.route("/menu")
def menu():
    category = request.args.get("category", "All")
    allowed_categories = {"All", "Meals", "Quick Bites", "Drinks", "Desserts"}
    if category not in allowed_categories:
        category = "All"
    q = request.args.get("q", "").strip().lower()[:80]
    shown = [m for m in MENU if (category == "All" or m["category"] == category)
             and (not q or q in m["name"].lower() or q in m["description"].lower())]
    return render_template(
        "menu.html", items=shown,
        categories=["All", "Meals", "Quick Bites", "Drinks", "Desserts"],
        selected=category, q=request.args.get("q", "")[:80],
    )


@app.post("/cart/add/<int:item_id>")
def add_to_cart(item_id):
    if not any(m["id"] == item_id for m in MENU):
        abort(404)
    cart_data = session.get("cart", {})
    key = str(item_id)
    try:
        cart_data[key] = min(int(cart_data.get(key, 0)) + 1, 20)
    except (TypeError, ValueError):
        cart_data[key] = 1
    session["cart"] = cart_data
    flash("Added to your cart.")
    return redirect(url_for("menu"))


@app.route("/cart")
def cart():
    items, total = cart_details()
    return render_template("cart.html", items=items, total=total)


@app.post("/cart/update")
def update_cart():
    cart_data = session.get("cart", {})
    for key in list(cart_data):
        try:
            qty = int(request.form.get(key, 0))
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            cart_data.pop(key, None)
        else:
            cart_data[key] = min(qty, 20)
    session["cart"] = cart_data
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, total = cart_details()
    if not items:
        flash("Your cart is empty.")
        return redirect(url_for("menu"))

    if request.method == "POST":
        customer = request.form.get("customer", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        payment_key = request.form.get("payment_method", "")
        if (not customer or len(customer) > 80
                or not re.fullmatch(r"[0-9+() -]{7,20}", phone)
                or not address or len(address) > 500):
            flash("Enter a name (up to 80 characters), a valid phone number and an address (up to 500 characters).")
            return render_template("checkout.html", items=items, total=total)
        if payment_key not in PAYMENT_METHODS:
            flash("Choose Razorpay or Cash on Delivery.")
            return render_template("checkout.html", items=items, total=total)

        summary = "; ".join(f'{item["name"]} x{item["qty"]}' for item in items)
        items_json = json.dumps(
            [{"name": item["name"], "qty": item["qty"], "unit_price": item["price"],
              "subtotal": item["subtotal"]} for item in items],
            ensure_ascii=False,
        )
        receipt_token = secrets.token_urlsafe(24)

        if payment_key == "cod":
            transaction_id = f"COD-{secrets.token_hex(5).upper()}"
            with db() as conn:
                cursor = conn.execute(
                    """INSERT INTO orders
                       (customer, phone, address, items, total, payment_method,
                        payment_status, transaction_id, receipt_token, items_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (customer, phone, address, summary, total, PAYMENT_METHODS["cod"],
                     "Payment due on delivery", transaction_id, receipt_token, items_json),
                )
                order_id = cursor.lastrowid
            session["cart"] = {}
            return redirect(url_for("receipt", order_id=order_id, token=receipt_token))

        key_id = os.environ.get("RAZORPAY_KEY_ID")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
        if not key_id or not key_secret:
            flash("Online payments are temporarily unavailable. Please choose Cash on Delivery.")
            return render_template("checkout.html", items=items, total=total)

        try:
            client = razorpay.Client(auth=(key_id, key_secret))
            gateway_order = client.order.create(data={
                "amount": int(total * 100),
                "currency": "INR",
                "receipt": f"homeeats-{secrets.token_hex(8)}",
                "notes": {"customer": customer[:80], "phone": phone[:20]},
            })
            gateway_order_id = gateway_order["id"]
            with db() as conn:
                conn.execute(
                    """INSERT INTO orders
                       (customer, phone, address, items, total, payment_method,
                        payment_status, receipt_token, items_json, gateway_order_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (customer, phone, address, summary, total, PAYMENT_METHODS["razorpay"],
                     "Payment pending", receipt_token, items_json, gateway_order_id),
                )
            options = {
                "key": key_id,
                "amount": int(total * 100),
                "currency": "INR",
                "name": "HomeEats",
                "description": "Home-cooked meal order",
                "order_id": gateway_order_id,
                "prefill": {"name": customer, "contact": phone},
                "theme": {"color": "#355b45"},
            }
            return render_template(
                "checkout.html", items=items, total=total,
                razorpay_options=options,
            )
        except Exception:
            app.logger.exception("Razorpay order creation failed")
            flash("We couldn't start the payment. Your cart is safe; please try again or choose Cash on Delivery.")
            return render_template("checkout.html", items=items, total=total)

    return render_template("checkout.html", items=items, total=total)


@app.post("/payment/verify")
def verify_payment():
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    gateway_order_id = request.form.get("razorpay_order_id", "")
    payment_id = request.form.get("razorpay_payment_id", "")
    signature = request.form.get("razorpay_signature", "")
    if not key_id or not key_secret or not gateway_order_id or not payment_id or not signature:
        abort(400, description="Payment verification details are incomplete.")

    with db() as conn:
        order = conn.execute(
            "SELECT * FROM orders WHERE gateway_order_id = ?", (gateway_order_id,)
        ).fetchone()
    if not order or order["payment_status"] == "Paid":
        abort(400, description="This payment order is invalid or already processed.")

    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        client.utility.verify_payment_signature({
            "razorpay_order_id": gateway_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })
        payment = client.payment.fetch(payment_id)
        expected_amount = int(round(float(order["total"]) * 100))
        if (payment.get("order_id") != gateway_order_id
                or int(payment.get("amount", -1)) != expected_amount
                or payment.get("currency") != "INR"):
            abort(400, description="Payment details do not match this order.")
        if payment.get("status") == "authorized":
            client.payment.capture(payment_id, expected_amount)
            payment = client.payment.fetch(payment_id)
        if payment.get("status") != "captured":
            flash("Payment has not been captured yet. Please contact support before retrying.")
            return redirect(url_for("checkout"))

        with db() as conn:
            conn.execute(
                """UPDATE orders SET payment_status = ?, transaction_id = ?,
                   gateway_payment_id = ? WHERE id = ? AND gateway_order_id = ?""",
                ("Paid", payment_id, payment_id, order["id"], gateway_order_id),
            )
        session["cart"] = {}
        return redirect(url_for(
            "receipt", order_id=order["id"], token=order["receipt_token"]
        ))
    except HTTPException:
        raise
    except razorpay.errors.SignatureVerificationError:
        abort(400, description="Payment signature verification failed.")
    except Exception:
        app.logger.exception("Razorpay payment verification failed")
        flash("We couldn't confirm this payment. Please contact support with your payment reference.")
        return redirect(url_for("checkout"))


@app.route("/receipt/<int:order_id>/<token>")
def receipt(order_id, token):
    with db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order or not order["receipt_token"] or not hmac.compare_digest(order["receipt_token"], token):
        abort(404)
    try:
        receipt_items = json.loads(order["items_json"])
    except (TypeError, json.JSONDecodeError):
        receipt_items = []
    return render_template("receipt.html", order=order, items=receipt_items)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        return "Admin dashboard is disabled. Set ADMIN_PASSWORD in your environment.", 503
    if request.method == "POST":
        if request.form.get("password") == password:
            session.clear()
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Incorrect password.")
    if not session.get("admin"):
        return render_template("admin_login.html")
    with db() as conn:
        orders = conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 100").fetchall()
    return render_template("admin.html", orders=orders)


@app.post("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("home"))


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0",
            port=int(os.environ.get("PORT", 5000)))
