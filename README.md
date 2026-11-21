# HomeEats — Homestyle Food Ordering

HomeEats is a responsive, server-rendered food discovery and ordering demo built with **Python, Flask, SQLite, HTML and CSS**. It brings a simple homestyle food catalogue, shopping cart and order workflow into one small full-stack project.

## Features

- Responsive landing page and menu catalogue
- Menu categories and keyword search
- Session-based shopping cart with quantity updates
- Checkout form with basic validation
- Orders persisted in SQLite
- Optional password-protected admin dashboard to review recent orders
- No payment processing; checkout is a portfolio/demo flow

## Tech stack

- Python 3.10+
- Flask
- SQLite
- Jinja templates
- HTML5 and CSS3

## Run locally

1. Clone the repository:
   ```bash
   git clone https://github.com/Mannn2105/Home--eats.git
   cd Home--eats
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS / Linux
   source .venv/bin/activate
   ```
3. Install dependencies and start the app:
   ```bash
   pip install -r requirements.txt
   python app.py
   ```
4. Open http://127.0.0.1:5000

The SQLite database is created automatically as `homeeats.db` on first run.

## Admin dashboard

Set an environment variable named `ADMIN_PASSWORD` before starting the app to enable the dashboard at `/admin`.

Windows PowerShell:
```powershell
$env:ADMIN_PASSWORD="choose-a-strong-password"
$env:SECRET_KEY="replace-with-a-long-random-secret"
python app.py
```

macOS / Linux:
```bash
export ADMIN_PASSWORD="choose-a-strong-password"
export SECRET_KEY="replace-with-a-long-random-secret"
python app.py
```

If `ADMIN_PASSWORD` is not configured, the admin dashboard remains disabled. Never commit real secrets to GitHub. For a public deployment, configure a strong `SECRET_KEY`, disable Flask debug mode, use HTTPS, and configure persistent storage for SQLite or migrate to a managed database.

## Project structure

```text
Home--eats/
├── app.py
├── requirements.txt
├── static/
│   └── style.css
└── templates/
    ├── base.html
    ├── index.html
    ├── menu.html
    ├── cart.html
    ├── checkout.html
    ├── success.html
    ├── admin_login.html
    └── admin.html
```

## Notes and limitations

This is an educational portfolio project, not a production food-delivery platform. It does not process payments, send notifications, provide customer accounts, or integrate live restaurant inventory. Customer/order data is stored locally in SQLite. Add CSRF protection, stronger validation, rate limiting, production session settings and a managed database before exposing it to real customers.

## Author

Built by [@Mannn2105](https://github.com/Mannn2105).
