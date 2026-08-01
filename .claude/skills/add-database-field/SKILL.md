---
name: add-database-field
description: Workflow and gotchas for adding or changing a column on any model in models.py in MotoSparePartsERP — migration generation, SQLite ALTER TABLE limits, and the recalc-on-assignment trap. Use whenever a task requires touching models.py.
---

# Adding/changing a database field

This project has one `models.py` for every table (no per-domain model files) and uses Flask-Migrate/Alembic against a single SQLite file at `instance/erp.db`. See [models.py](../../../models.py).

## Procedure

1. Edit the model class in `models.py` — add the `db.Column(...)`, or change an existing one.
2. Generate the migration:
   ```
   set FLASK_APP=app.py
   flask db migrate -m "describe your change"
   ```
3. **Always open the generated file in `migrations/versions/` and read it before applying.** Alembic's autogenerate is not reliable for SQLite: it sometimes misses column-type changes, misses server defaults for existing rows, or drops/recreates a table it didn't need to. Fix by hand if the diff doesn't match your intent.
4. Apply it: `flask db upgrade`.
5. If the new column is `nullable=False` and the table already has rows, either give it a `server_default` in the migration or backfill existing rows in the same migration before making it non-nullable — SQLite will otherwise reject the migration or silently insert NULLs depending on the op.

## Gotchas specific to this repo

- **Adding a unique column that should allow multiple blanks** (e.g. an optional barcode/reference field): use `nullable=True` — SQLite treats multiple `NULL`s as distinct under a unique constraint, so this is safe and does not need a workaround.
- **Computed values are not automatic.** `Product.recalc_prices()` must be called explicitly after changing `mrp` or `actual_discount_pct` — assigning the columns directly does not recompute `actual_discounted_price`. If your field change interacts with pricing, check whether existing call sites (`routes/products.py`, `routes/purchases.py::Product.update_cost_from_purchase`) need updating too.
- **Don't forget the two other places a new column usually needs to show up:**
  - Excel mirror — see [[add-exportable-table]] (`excel_sync.py`'s `SHEETS` dict).
  - CSV export — see [[add-exportable-table]] (`routes/settings.py`'s `EXPORTABLE` dict).
- If the field is user-entered via an HTML form, see [[new-form-checklist]] for the CSRF-token and date-parsing traps that apply to every form in this codebase.
