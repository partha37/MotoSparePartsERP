# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Flask-based inventory, billing, and tracking ERP for a two-wheeler spare parts shop (multi-brand: Honda, TVS, Bajaj) in Tamil Nadu. Single-shop, single-user, offline-first — runs locally, no cloud hosting, no JS build step. Server-rendered pages only.

## Commands

```
# first-time setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set FLASK_APP=app.py
flask db upgrade

# run the app
venv\Scripts\activate
python app.py
# open http://127.0.0.1:5000 — first visit prompts you to create the shop-owner login

# after changing models.py
set FLASK_APP=app.py
flask db migrate -m "describe your change"
flask db upgrade
```

There is no test suite, linter, or build step configured.

## Architecture

**App factory + blueprints.** `app.py` defines `create_app()`, initializes `db`/`migrate`/`login_manager`/`csrf` from `extensions.py`, and registers one blueprint per domain from `routes/` (auth, dashboard, products, suppliers, purchases, customers, mechanics, sales, stock, reports, settings). Each blueprint owns its own templates under `templates/<blueprint>/`.

**Single `models.py`** holds all SQLAlchemy models — no per-domain model files. Key relationships:
- `Product` is the master record with the shop's specific pricing model: `mrp`, `actual_discount_pct`/`actual_discounted_price` (cost from distributor), `selling_discount_pct`/`mrp_discounted_price` (price charged to customer — deliberately distinct from cost). Call `product.recalc_prices()` after changing `mrp`/`actual_discount_pct`/`selling_discount_pct` — it's not automatic on assignment. `margin_per_unit` and `is_low_stock` are computed properties, not columns.
- `Purchase`/`PurchaseItem` (stock-in) and `Sale`/`SaleItem` (stock-out) are header/line-item pairs. Saving either must also update `Product.current_stock` directly and insert a matching `StockMovement` row — this isn't automatic (see `routes/purchases.py::new_purchase` and `routes/sales.py::new_sale` for the pattern to follow).
- `StockMovement` is the single source of truth for day-wise tracking (`routes/stock.py`) — every stock change must write one row here with `type` (`purchase_in`/`sale_out`/`adjustment`/`return`) and a signed `qty`.
- Mechanic-wise/customer-wise reporting is just `Sale` filtered by `mechanic_id`/`customer_id` — there's no separate tracking table.
- GST on a sale is computed per line (`SaleItem.gst_amount`/`line_total`) from the product's `gst_rate` at sale time, not recalculated from current product data later.
- `Sale.invoice_no` is generated as `INV-{id:05d}` via `routes/sales.py::_next_invoice_no()`.

**Forms are plain HTML + `request.form`, not Flask-WTF form classes.** CSRF protection is global (`CSRFProtect` in `extensions.py`), but every `<form method="post">` must manually include `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` — nothing adds this automatically, including forms that are just a delete button in a list template. Missing this causes a 400 on submit.

**Dates from HTML `<input type="date">` come in as ISO strings and must be converted with `date.fromisoformat(...)` before assigning to a `db.Date` column** (e.g. `Purchase.date`, `Sale.date`, `StockMovement.date`) — SQLite's date type raises `TypeError` on raw strings at insert/update time. Filtering/comparing an existing `Date` column against a plain ISO string in a `WHERE` clause (as `routes/stock.py` and `routes/reports.py` do for date-range filters) works fine and does not need this conversion.

**Deletion guards.** Products/Suppliers/Customers/Mechanics cannot be deleted if referenced by any Purchase/Sale line item — each `delete_*` route checks for this and flashes an error instead of relying on DB foreign-key enforcement (SQLite FKs aren't enforced by default here).

**CSV export / DB backup** (`routes/settings.py`) — `EXPORTABLE` dict maps table name → `(model, [columns])`; add new exportable tables there. Backup just serves `instance/erp.db` directly as a file download, so exports.

## Data notes

- `instance/erp.db` is gitignored (per-shop data, never commit it).
- Auth is a single shop-owner account; `routes/auth.py` redirects to `/auth/setup` to create it if `User.query.count() == 0`, otherwise to `/auth/login`.
- Profit-margin report (`routes/reports.py::profit_margin`) uses each product's *current* `actual_discounted_price` as cost, not the historical purchase price at time of sale — a known simplification.
