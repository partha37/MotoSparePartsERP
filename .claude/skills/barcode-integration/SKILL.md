---
name: barcode-integration
description: Implementation plan for barcode-scanner-driven stock-in (Purchases) and stock-out (Sales) in MotoSparePartsERP — scan-to-add inventory, scan-to-bill at checkout, repeat-scan increments quantity like a retail POS. Use this skill whenever building, extending, or debugging barcode/scanner features in this repo.
---

# Barcode integration plan (MotoSparePartsERP)

## Design decisions (agreed with the shop owner)

- The scanner reads the **part number itself** as the barcode payload — not a separate barcode code. `Product.part_no` in [models.py](../../../models.py) is already `unique=True, index=True`, so **no new DB column or migration is needed** for this to work. A barcode sticker just needs to encode the existing `part_no` string (Code128 handles alphanumeric).
- Hardware assumption: a USB/Bluetooth barcode scanner in HID keyboard-wedge mode — it types the scanned text followed by Enter into whatever input has focus. No drivers, no camera JS, nothing that violates the "no JS build step, offline-first" rule in [CLAUDE.md](../../../CLAUDE.md).
- **Repeat-scan increments quantity — like a retail checkout.** Scanning the same part_no again within the same in-progress invoice does NOT add a duplicate line; it bumps that existing line's Qty by 1. This applies to both Purchases (receiving 20 units = scan 20 times) and Sales (customer buying 3 identical items = scan 3 times). Manual typing into the Qty field must remain possible too (e.g. receiving 500 sealed washers — nobody scans 500 times), so scan-increment and manual edit both write to the same field, never conflicting.
- Price is never encoded in a barcode and is always a manual entry — one per product line, not per unit.
- Scanning is **additive**, not a replacement for the existing dropdowns in [templates/purchases/form.html](../../../templates/purchases/form.html) and [templates/sales/form.html](../../../templates/sales/form.html). Anything not yet labeled still works via the manual product-select flow.
- If a scanned part_no has no matching Product, surface "Unknown part, add it first" with a link to the product-add form pre-filled with the scanned code as `part_no` — don't silently fail or auto-create a product.

## New since this plan was written — two things the scan box must account for

The sales/purchases forms got a UI upgrade after this plan was drafted (see [[ui-visual-conventions]] for full detail). Both directly affect how the scan box has to be built:

1. **Every `<select>` is now a searchable-select combobox** (`static/js/searchable-select.js`, `window.SearchableSelect`), including the product and batch dropdowns the scan box will drive. Auto-selecting a product/batch from JS (as Steps 2–3 below do) must call `.refreshSearchable()` on that select right after setting `.value`/`.selectedIndex`, or the visible proxy input will show stale/blank text while the real value is actually correct — see the existing `if (batchSelect.refreshSearchable) batchSelect.refreshSearchable();` call in `templates/sales/form.html` for the pattern. Likewise, when cloning a template row for a newly-scanned product, call `SearchableSelect.reset(newRow)` before re-selecting elements and re-enhancing them — cloneNode copies the enhanced markup but not its JS state.
2. **`base.html` now has a global "Enter advances to the next field" handler** on `document` (bubble phase): Enter in a text/number/date/email/tel/search input or select moves focus to the next field, or submits the form if there is none. The scan box is exactly a text input the scanner types into and terminates with Enter — **without intervention, that Enter will bubble up to this global handler after your scan-handling code runs, which will then also try to advance focus or submit the form early.** The scan box's own `keydown` listener must call `e.preventDefault()` **and** `e.stopPropagation()` so the global handler never sees it — don't rely on `preventDefault()` alone, since `stopPropagation()` is the one that actually stops the bubbling document listener from firing.

## Step 1 — Shared lookup endpoint (build first)

Add one route, e.g. in `routes/products.py`:

```
GET /products/lookup?code=<scanned_text>
```

- Looks up `Product.query.filter_by(part_no=code).first()`.
- Returns JSON `{id, product_name, part_no, available_batches}` on success (reuse whatever shape `_attach_available_batches()` already produces in [routes/sales.py](../../../routes/sales.py), since the sales form's existing JS already expects a `data-batches` JSON blob per product).
- Returns 404 JSON `{"error": "not_found"}` if no match — the frontend uses this to show the "add product first" prompt.

Both scan boxes below call this same endpoint.

## Step 2 — Sales scan box (build second — biggest daily time save)

In [templates/sales/form.html](../../../templates/sales/form.html):

1. Add an auto-focused "Scan Barcode" text input above `#itemsTable`.
2. On Enter keypress (with `preventDefault()` + `stopPropagation()` per above): AJAX GET to the lookup endpoint with the scanned text.
3. **If a row for this product+batch already exists in the table**, increment that row's `.qty-input` value by 1 (respecting the existing `qtyInput.max` cap tied to batch stock at [templates/sales/form.html:207](../../../templates/sales/form.html#L207)) and call `recalcLine()`.
4. **Otherwise**, clone the existing empty row the same way `#addRow` does — including its `SearchableSelect.reset(newRow)` call before touching anything inside the clone — select the matched product on the row's `.product-select` (submitted as `product_filter[]`; it only drives which batches get listed, it is *not* the value the server reads), and reuse `populateBatches()` / `updatePriceFromBatch()` so the oldest batch and its price auto-fill exactly like a manual selection would. Remember the `.refreshSearchable()` call on both `.product-select` and `.batch-select` after setting them programmatically.
5. Clear the scan box and refocus it after every scan so the cashier can keep scanning without touching the mouse.
6. Do not change `routes/sales.py::new_sale` — it already reads `purchase_item_id[]` (not the product select) + `qty[]` + `selling_price[]` per line regardless of how the row was populated.

## Step 3 — Purchases scan box (build third)

In [templates/purchases/form.html](../../../templates/purchases/form.html), mirror Step 2 but against `routes/purchases.py::new_purchase`'s row structure — note this form's product select is `name="product_id[]"` (submitted directly, unlike the sales form's UI-only `product_filter[]`), and its clone-on-add-row already does `SearchableSelect.reset(newRow)` the same way, so follow that exact pattern:

1. Same auto-focused scan box, with the same `preventDefault()` + `stopPropagation()` requirement on Enter.
2. First scan of a part_no in this purchase → clone the template row (`SearchableSelect.reset()` first, same as `#addRow` does), select the matched product on `.product-select` and call `.refreshSearchable()`, Qty = 1, Purchase Price left blank for manual entry.
3. Repeat scan of the same part_no in this purchase → bump that row's Qty by 1.
4. Qty field stays freely editable by hand for bulk receipts.
5. Do not change `routes/purchases.py::new_purchase`'s save logic — it already creates the `PurchaseItem` batch, updates `Product.current_stock`, writes a `StockMovement`, and calls `Product.update_cost_from_purchase()` per line; scanning only changes how each line's product gets selected.

## Step 4 — Label printing (phase 2, once Steps 1–3 work)

For parts that don't already have a usable printed barcode:

1. Add `python-barcode` to [requirements.txt](../../../requirements.txt) (pure Python, generates Code128 SVG/PNG, no internet call — fits offline-first).
2. New route, e.g. `/products/<id>/label`, rendering a barcode image encoding `part_no` + product name + MRP, laid out for sticker-sheet printing via the browser's normal print dialog (Ctrl+P) — no new printer driver.

## Build order

1. Lookup-by-`part_no` endpoint.
2. Sales scan box + repeat-scan-increments-qty.
3. Purchases scan box + repeat-scan-increments-qty.
4. Label-printing route for un-stickered stock.

## Out of scope / explicitly rejected

- A separate `barcode` column distinct from `part_no` — rejected because the shop owner confirmed the scanner reads the part number directly; don't add one unless a future need for manufacturer-specific EAN codes that differ from `part_no` comes up.
- Typing quantity manually as the default for either Purchases or Sales — rejected in favor of repeat-scan-increments, matching retail POS behavior. Manual Qty entry remains available as a fallback, not the primary path.
