---
name: stock-mutation-checklist
description: The three things that must happen together whenever a route changes how much stock exists in MotoSparePartsERP — updating Product.current_stock, writing a StockMovement row, and syncing Excel. Use whenever adding or editing any route that creates, edits, or deletes a Purchase, Sale, or manual stock adjustment.
---

# Stock mutation checklist

Nothing in this codebase makes stock changes automatic — every route that changes how much of a product exists must do all three of the following in the same commit. See [models.py](../../../models.py) for `Product`, `PurchaseItem`, `StockMovement`.

## The three required steps

1. **Update `Product.current_stock` directly.** There is no trigger or hybrid property that keeps this in sync — it's a plain column that the route code must increment/decrement by hand. Purchases increase it, sales decrease it, adjustments/returns move it either way.
2. **Insert a matching `StockMovement` row.** This table is the single source of truth for day-wise tracking (`routes/stock.py`). Every row needs:
   - `type`: one of `purchase_in`, `sale_out`, `adjustment`, `return`
   - `qty`: **signed** — positive for stock coming in, negative for stock going out
   - `reference_type` / `reference_id`: pointing back at the Purchase/Sale/adjustment that caused it
3. **Call `sync_to_excel()` from `excel_sync.py`** after the commit — every existing mutating route already does this; new ones must follow the same pattern so `instance/erp_data.xlsx` doesn't drift from the DB. It's best-effort and never raises (it catches its own errors and flashes a warning, e.g. if the file is open in Excel), so call it plainly with no try/except wrapper — see [[add-exportable-table]].

## If the change is batch-aware (FIFO stock batches)

`PurchaseItem` doubles as a sellable batch (`remaining_qty`, `mrp_at_purchase`, `stock_number`, `effective_mrp`). If your route creates a purchase line, `remaining_qty` must start equal to `qty`. If it's a sale line, it must decrement the *specific* `PurchaseItem.remaining_qty` referenced by `purchase_item_id` — never subtract from a different batch or from the product's aggregate stock alone. `routes/sales.py::new_sale` blocks the whole sale if the chosen batch doesn't have enough `remaining_qty`; follow that same all-or-nothing validation pattern rather than allowing partial/cross-batch fulfillment.

## Reference implementations to copy from

- `routes/purchases.py::new_purchase` — stock-in pattern, plus `Product.update_cost_from_purchase()` for updating the product's headline cost/MRP.
- `routes/sales.py::new_sale` and `_attach_available_batches()` — stock-out pattern with FIFO batch selection.

## Common mistake to avoid

Updating `Product.current_stock` but forgetting the `StockMovement` row (or vice versa) is the single easiest way to make the day-wise report in `routes/stock.py` disagree with the product's stock count. Always grep for both when reviewing a new stock-affecting route.
