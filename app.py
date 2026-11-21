import os
import re
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort

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
MENU = [
    {"id": 1, "name": "Gujarati Thali", "category": "Meals", "description": "Rotli, shaak, dal, rice and a little sweetness.", "price": 149, "emoji": "🍱", "tag": "Bestseller"},
    {"id": 2, "name": "Punjabi Chole Bowl", "category": "Meals", "description": "Slow-cooked chole with jeera rice and salad.", "price": 129, "emoji": "🥘", "tag": "Comfort food"},
    {"id": 3, "name": "Paneer Wrap", "category": "Quick Bites", "description": "Spiced paneer, crunchy vegetables and mint chutney.", "price": 99, "emoji": "🌯", "tag": "Popular"},
    {"id": 4, "name": "Masala Khichdi", "category": "Meals", "description": "Homestyle moong dal khichdi with kadhi.", "price": 109, "emoji": "🍲", "tag": "Homestyle"},
    {"id": 5, "name": "Veg Sandwich", "category": "Quick Bites", "description": "Toasted sandwich with fresh vegetables and cheese.", "price": 79, "emoji": "🥪", "tag": ""},
    {"id": 6, "name": "Mango Lassi", "category": "Drinks", "description": "Chilled yoghurt drink blended with mango.", "price": 59, "emoji": "🥭", "tag": ""},
    {"id": 7, "name": "Gulab Jamun", "category": "Desserts", "description": "Two soft, syrup-soaked festive favourites.", "price": 49, "emoji": "🍮", "tag": ""},
    {"id": 8, "name": "Masala Chaas", "category": "Drinks", "description": "Refreshing spiced buttermilk.", "price": 35, "emoji": "🥛", "tag": "Refreshing"},
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
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer TEXT NOT NULL,
            phone TEXT NOT NULL, address TEXT NOT NULL, items TEXT NOT NULL,
            total REAL NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

def cart_details():
    cart = session.get("cart", {})
    items, total = [], 0
    for item in MENU:
        try:
            qty = max(0, min(int(cart.get(str(item["id"]), 0)), 20))
        except (TypeError, ValueError):
            qty = 0
        if qty > 0:
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
    return render_template("menu.html", items=shown, categories=["All", "Meals", "Quick Bites", "Drinks", "Desserts"], selected=category, q=request.args.get("q", ""))

@app.post("/cart/add/<int:item_id>")
def add_to_cart(item_id):
    if not any(m["id"] == item_id for m in MENU):
        abort(404)
    cart = session.get("cart", {})
    key = str(item_id)
    cart[key] = min(int(cart.get(key, 0)) + 1, 20)
    session["cart"] = cart
    flash("Added to your cart.")
    return redirect(url_for("menu"))

@app.route("/cart")
def cart():
    items, total = cart_details()
    return render_template("cart.html", items=items, total=total)

@app.post("/cart/update")
def update_cart():
    cart = session.get("cart", {})
    for key in list(cart):
        try:
            qty = int(request.form.get(key, 0))
        except ValueError:
            qty = 0
        if qty <= 0:
            cart.pop(key, None)
        else:
            cart[key] = min(qty, 20)
    session["cart"] = cart
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
        if (not customer or len(customer) > 80 or not re.fullmatch(r"[0-9+() -]{7,20}", phone)
                or not address or len(address) > 500):
            flash("Enter a name (up to 80 characters), a valid phone number and an address (up to 500 characters).")
            return render_template("checkout.html", items=items, total=total)
        summary = "; ".join(f'{i["name"]} x{i["qty"]}' for i in items)
        with db() as conn:
            cur = conn.execute("INSERT INTO orders (customer, phone, address, items, total) VALUES (?, ?, ?, ?, ?)",
                               (customer, phone, address, summary, total))
            order_id = cur.lastrowid
        session["cart"] = {}
        return render_template("success.html", order_id=order_id, total=total)
    return render_template("checkout.html", items=items, total=total)

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
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
