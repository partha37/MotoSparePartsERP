---
name: add-exportable-table
description: How to wire a new or changed model into CSV export and the Excel mirror in MotoSparePartsERP. Use whenever a new model/table is added, or an existing model gets a new column that should be visible in exports.
---

# Adding a table/column to CSV export and Excel mirror

This project keeps two independent, hand-maintained mappings that must both be updated whenever a model changes shape. Neither is automatic — a new column on a model does not appear in exports until you add it here. See [CLAUDE.md](../../../CLAUDE.md) for the source-of-truth description.

## 1. CSV export — `routes/settings.py`

Add/update the entry in the `EXPORTABLE` dict: `table name → (model, [columns])`. The columns list controls exactly what gets written to the CSV, in order.

## 2. Excel mirror — `excel_sync.py`

Add/update the entry in the `SHEETS` dict: `sheet name → (model, [columns])`. `sync_to_excel()` rewrites `instance/erp_data.xlsx` (one sheet per table) from current DB state and must be called after every mutating commit — see [[stock-mutation-checklist]] for the routes that need this. `ShopSettings` is written as its own sheet by hand inside `_write_workbook()`, not through the `SHEETS` dict (it's a single-row table) — follow that pattern only if you add another genuinely single-row table; everything else goes in `SHEETS`.

### `sync_to_excel()` is best-effort and never raises — call it plainly

`_cell_value()` looks up `getattr(row, col, _MISSING)` first; only if the row has no such attribute does it fall through to `_DERIVED`. `sync_to_excel()` itself catches `PermissionError` (the workbook is open/locked in Excel on Windows) and any other exception, flashing a warning instead of raising. **This means routes should just call `sync_to_excel()` after `db.session.commit()` with no try/except of their own** — wrapping it defensively would be redundant, and swallowing its (already-swallowed) errors silently would hide the flash message the user is supposed to see.

### The `_DERIVED` fallback trap

Columns not present as a real attribute on the row fall back to `_DERIVED` (e.g. `product_name` resolved via a `.product` relationship on a line-item model). **Only fall back to `_DERIVED` if the row itself has no real attribute of that name.** Checking `_DERIVED` *before* the row's own attributes was a real bug in this codebase: it broke the `Products` sheet, because `product_name` is a genuine column on `Product` itself, and that lookup collided with the same key meaning "resolve via relationship" on other sheets (e.g. `SaleItem`, `PurchaseItem`). The current `_cell_value()` implementation already gets this order right — don't invert it while touching this file.

## Checklist when adding a new model entirely

1. Model defined in `models.py`, migration applied (see [[add-database-field]]).
2. Entry added to `EXPORTABLE` in `routes/settings.py`.
3. Entry added to `SHEETS` in `excel_sync.py` (or hand-written alongside `ShopSettings` if it's a genuine single-row table), with any relationship-derived columns going through `_DERIVED` correctly.
4. Confirm any route that creates/edits/deletes rows of this model calls `sync_to_excel()` after commit, with no extra error handling around the call.
