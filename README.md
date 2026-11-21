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

The SQLite database is created automatically at `data/homeeats.db` on first run. Set `DATA_DIR` to change its location.

## Run tests

Run the automated application tests with:

```bash
python -m unittest discover -s tests -v
```

The suite covers page rendering, menu search, cart updates, checkout persistence, invalid input, CSRF rejection and the disabled-by-default admin route.

## Production deployment

The live demo is deployed on Railway: https://homeeats-web-production.up.railway.app

The production service runs with Gunicorn. Its SQLite database directory is mounted to a persistent Railway volume at `/app/data`, so order records survive application redeployments. The app uses a generated `SECRET_KEY`, secure session-cookie settings and CSRF tokens for form submissions. The admin dashboard is disabled unless `ADMIN_PASSWORD` is explicitly configured.

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

If `ADMIN_PASSWORD` is not configured, the admin dashboard remains disabled. Never commit real secrets to GitHub. For any deployment, use HTTPS, keep Flask debug mode off, configure a strong `SECRET_KEY`, and ensure `DATA_DIR` points to persistent storage. For a larger production workload, migrate SQLite to a managed database.

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
