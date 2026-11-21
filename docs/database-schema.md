# HomeEats Database Schema

HomeEats currently uses one persistent SQLite table: `orders`.

| Field | Type | Notes |
|---|---|---|
| id | INTEGER PRIMARY KEY | Auto-increment order number |
| customer | TEXT NOT NULL | Delivery recipient |
| phone | TEXT NOT NULL | Contact number |
| address | TEXT NOT NULL | Delivery address |
| items | TEXT NOT NULL | Readable item summary |
| items_json | TEXT NOT NULL | JSON snapshot of line items and prices |
| total | REAL NOT NULL | Server-calculated total in INR |
| payment_method | TEXT NOT NULL | UPI (Demo), Card (Demo), Cash on Delivery |
| payment_status | TEXT NOT NULL | Simulated success or due on delivery |
| transaction_id | TEXT | Demo/COD reference; not a real processor transaction |
| receipt_token | TEXT | Random token used to protect receipt access; unique index |
| created_at | TIMESTAMP | Defaults to SQLite current timestamp |

## Relationships

There are no separate customer, product or payment-provider tables in this MVP. The menu is a server-side Python catalogue, and each order stores a snapshot of the purchased line items so later menu edits do not change an existing receipt.

## Migration behaviour

At startup, `init_db()` creates the orders table if it does not exist, inspects the existing columns and adds missing payment and receipt fields with safe defaults. Existing order rows are preserved.
