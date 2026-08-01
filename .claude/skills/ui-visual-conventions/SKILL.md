---
name: ui-visual-conventions
description: Visual/component conventions for MotoSparePartsERP's server-rendered Bootstrap 5 UI — cards, tables, print styling, flash alerts, color usage. Use whenever adding or restyling a template so new pages look and behave like the rest of the app rather than introducing a one-off style.
---

# UI visual conventions

This app is server-rendered Jinja2 + Bootstrap 5 — **no JS build step, no npm.** There *is* now a small custom design system layered on top of stock Bootstrap (brand colors, an inlined-SVG icon helper, a searchable-select combobox) — described below. Every new template should look like it was built by the same person who built [templates/base.html](../../../templates/base.html), not introduce a new pattern. The shop's displayed name is "Lokey Auto Spare Parts" (page titles, navbar brand) — the repo/codebase is still called MotoSparePartsERP; don't confuse the two when writing user-facing text.

## Assets are vendored locally — never reintroduce a CDN

Bootstrap CSS/JS lives at `static/vendor/bootstrap/{css,js}/` and [templates/base.html](../../../templates/base.html) loads it via `url_for('static', filename='vendor/bootstrap/...')`. This was a deliberate fix — it used to load from the jsdelivr CDN, which broke all styling and Bootstrap JS (navbar toggle, dropdowns, dismissible alerts) whenever the shop's internet was down, directly contradicting the offline-first requirement in [CLAUDE.md](../../../CLAUDE.md). **Any new frontend dependency (icon font, chart library, additional JS plugin, a barcode-scanning JS lib, etc.) must be vendored into `static/vendor/<name>/` the same way — never add a `<link>`/`<script>` pointing at a CDN**, even "just for now." If you see one, that's a regression back to the pre-fix state, not a shortcut.

## Icon system — inlined SVGs via the `icon()` helper, not a font/CDN

`app.py`'s `inject_icon_helper()` context processor exposes a Jinja global `icon(name, css_class="")` that reads `static/vendor/bootstrap-icons/<name>.svg`, caches it (`@lru_cache`), and returns it as inline `Markup` — e.g. `{{ icon('receipt', 'me-2') }}New Sale`. Icons are inlined SVG (not an icon font, not `<img>`) specifically so they inherit `currentColor` and work correctly in the dark navbar, colored buttons, and any future dark-mode without per-icon color overrides.

- **Only 43 icon names currently exist** in `static/vendor/bootstrap-icons/` (matching what's used in the templates so far). If you need a new icon, download that specific Bootstrap Icons SVG into that folder — don't reference a name that isn't there, since `_read_icon` silently returns an empty string (with a server-log warning) rather than failing loudly, so a typo'd icon name just renders nothing with no visible error.
- Usage pattern: icon first, text immediately after, inside the same element (`<h5>{{ icon('box-seam', 'me-1') }}Items</h5>`, `<button>{{ icon('save') }}Save</button>`) — spacing comes from the `.bi` CSS rules in `style.css` (`.nav-link .bi`, `.btn .bi`) plus an optional `me-*` class passed as the second argument, not manual margin on the icon itself unless overriding the default.
- Never add Bootstrap Icons via CDN/webfont or an `<i class="bi bi-...">` tag — that bypasses the `currentColor` theming and reintroduces a CDN dependency (see below).

## Brand color system — use Bootstrap classes/variables, never hardcode hex

`static/css/style.css` defines `--brand` (navy, #1e4b8c), `--brand-dark`, `--brand-light`, `--accent` (orange, #e8720c), `--accent-dark`, `--accent-light` as CSS custom properties, then overrides Bootstrap 5.3's per-component CSS variables (`.btn-primary`'s `--bs-btn-bg`, etc.) so standard Bootstrap classes automatically pick up the shop's brand colors without touching Bootstrap's own CSS file. **Practical rule: use `btn-primary`, `btn-outline-primary`, `text-primary`, links, etc. as normal — never write a hardcoded hex color or inline `style="color: ..."` in a template.** If a new component needs the brand/accent color, reference the CSS variable (`var(--brand)`, `var(--accent)`) in `style.css`, matching the existing pattern, rather than picking a new color.

## Required-field marker

`<label class="form-label required" for="f-xyz">Field Name</label>` — add the `required` class to a label (alongside `form-label`) whenever its input has the `required` attribute; CSS renders a colored asterisk via `label.required::after`. Every required input in [templates/products/form.html](../../../templates/products/form.html) follows this now (Product Name, Part No, MRP) — match it on new required fields rather than a manual `*` in the label text.

## Dashboard stat-card component

`.stat-card` (flex row) + `.stat-card-icon` (48px rounded icon tile, brand-tinted background) is the established pattern for KPI tiles — see [templates/dashboard/index.html](../../../templates/dashboard/index.html): `<div class="card p-3 stat-card"><div class="stat-card-icon">{{ icon('...') }}</div><div>...label/value...</div></div>`. Add `.accent` to `.stat-card-icon` for a warning/attention tile (orange tint instead of brand-blue) — used for the low-stock count when it's non-zero. Reuse this for any new dashboard summary number instead of a plain `.card p-3` text block.

## Searchable-select — every `<select>` gets this, not just line-item rows

`static/js/searchable-select.js` (loaded globally in `base.html`, exposes `window.SearchableSelect`) turns a plain `<select>` into a type-to-filter combobox: it hides the real `<select>`, overlays a text input + filtered dropdown list, and keeps the hidden select's `value`/`selectedIndex` and `change` event fully in sync — so all existing code that reads `select.value` or listens for `change` keeps working untouched. **This is now the default for every `<select>` in the app**, not an opt-in enhancement for special cases — customer, mechanic, payment-mode, product, batch, and unit dropdowns are all enhanced (see [templates/sales/form.html](../../../templates/sales/form.html), [templates/products/form.html](../../../templates/products/form.html)).

Three rules that are easy to get wrong when adding or touching a `<select>`:

1. **Enhance it explicitly.** Add `SearchableSelect.enhance(document.getElementById('f-whatever'))` (or `SearchableSelect.enhance(someSelectElement)`) in the page's inline `<script>` for every new `<select>` — it does not happen automatically just by existing in the DOM.
2. **Reset before re-wiring a cloned row.** `cloneNode(true)` copies the enhanced markup (the wrapper `<div>`, the hidden `<select>`, the proxy `<input>`) but not JS state/listeners, so a naively re-enhanced clone ends up double-wrapped and broken. Always call `SearchableSelect.reset(newRow)` on a cloned row **before** re-selecting elements inside it and calling `SearchableSelect.enhance()` again — see the `addRow` handler in `templates/sales/form.html` for the exact order.
3. **Call `.refreshSearchable()` after programmatically changing a value.** If code sets `select.value` or `select.selectedIndex` directly (auto-picking the oldest batch, resetting a batch list, a future barcode scan auto-selecting a product) without going through the proxy input, the visible text won't update unless you also call `select.refreshSearchable()` right after — every existing auto-select call site in `templates/sales/form.html` does this (`if (batchSelect.refreshSearchable) batchSelect.refreshSearchable();`); a new one that forgets it will show the wrong/blank text while the real value is actually correct, which is a confusing bug to track down.

Also note: options whose visible label starts with `--` (e.g. `-- Select Product --`) are treated as placeholder/prompt text, not a real committed value — keep that convention for any new "no selection yet" option.

## Global keyboard behavior: Enter advances to the next field

`base.html` attaches a document-level `keydown` listener: pressing Enter in a text/number/date/email/tel/search `<input>` or a `<select>` moves focus to the next visible, enabled field in the same form instead of submitting; the form only actually submits (`form.requestSubmit()`) once there's no next field. This is the app-wide mechanism for the keyboard-first data entry described in [[shop-counter-ux]] — Tab is not the primary way the owner is expected to move between fields, Enter is.

**This matters a lot for anything that wants to react to Enter itself** (most notably the planned barcode scan box in [[barcode-integration]]): because this listener is on `document` and fires on the bubble phase, a scan-box input's own `keydown` handler must call `e.stopPropagation()` (in addition to `e.preventDefault()` if it doesn't want default Enter behavior at all) — otherwise, after your handler runs, the event still bubbles up to this document listener, which will *also* try to advance focus or submit the form, undoing or conflicting with whatever the scan handler just did.

## Layout skeleton (established in base.html)

- `<nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4 no-print">` — one flat list of blueprint links, no dropdowns, no nesting. A new blueprint gets one more `<li class="nav-item">` here, not a submenu.
- `<div class="container-fluid px-4">` wraps all page content — full-width, not a centered fixed-width container. New pages should not wrap themselves in an additional `.container`.
- Flash messages render once, globally, in `base.html` via `alert alert-{{ category }} alert-dismissible fade show no-print` — never build a page-specific flash/toast mechanism; use `flash(message, category)` server-side and let the existing block render it.

## Component patterns already established — reuse, don't reinvent

- **Forms**: `<form method="post" class="card p-4">` wrapping a Bootstrap grid (`row g-3` / `col-md-*`) of labeled inputs (`form-label` + `form-control`/`form-select`). See [templates/products/form.html](../../../templates/products/form.html) as the reference example. Every input/select now gets an explicit `id="f-something"` matched by its `<label for="f-something">` — this isn't just accessibility polish, `SearchableSelect.enhance()` relies on the `for` attribute to make "click the label" focus the proxy input instead of the now-hidden real select. Fields inside a repeated table row (no visible label, e.g. a Qty cell) get `aria-label="..."` on the input itself instead.
- **Read-only computed fields**: rendered as `<input class="form-control" disabled>` inside the same grid, not as plain text — e.g. cost price / margin / current stock on the product form. Keeps disabled derived values visually consistent with editable ones instead of looking like an afterthought.
- **Line-item tables** (purchase/sale forms): `<table class="table" id="itemsTable">` with a template `<tr>` that gets cloned via JS for "+ Add Line", each row independently wired for its own event listeners. Don't build a different repeating-row pattern — copy the clone-and-rewire approach in [templates/sales/form.html](../../../templates/sales/form.html).
- **Cards**: plain `.card p-4`, no colored headers, no shadows beyond the subtle one already defined in [static/css/style.css](../../../static/css/style.css) (`box-shadow: 0 1px 3px rgba(0,0,0,0.08)`, `border: none`). Don't add Bootstrap's default bordered card style on top of this — it'll look inconsistent with every other card in the app.
- **Money formatting**: always `₹{{ "%.2f"|format(value) }}` — two decimals, rupee symbol, no thousands separator currently in use. Match this exactly rather than introducing `{{ "{:,.2f}".format(...) }}` style formatting on just one page.
- **Muted/help text**: `<div class="form-text">...</div>` under an input, or `<span class="text-muted small">...</span>` inline — used throughout to explain non-obvious fields (e.g. "Selling price is decided per sale at checkout, not fixed here" on the product form). New non-obvious fields should get the same treatment rather than relying on the user to guess.

## Print styling

`.no-print` (defined in `static/css/style.css`, `display: none !important` under `@media print`) hides chrome — nav, buttons, flash alerts — on anything meant to be printed (invoices, labels). Pattern: wrap the printable content in a plain `.card`, put every interactive element (buttons, nav, back-links) in a sibling element tagged `no-print`, and trigger printing with a plain `onclick="window.print()"` button — see [templates/sales/view.html](../../../templates/sales/view.html). Don't introduce a separate print-only template or an external PDF library; this in-page print-CSS approach is the established pattern and needs no dependencies.

## Stock/status color conventions

There's no dedicated low-stock badge/color convention yet in the codebase — if you add visual status indicators (e.g. highlighting `Product.is_low_stock`), use Bootstrap's existing semantic classes (`text-danger`, `badge bg-danger`/`bg-warning`) rather than inventing custom colors in `style.css`, so it stays visually consistent with flash-message categories (`alert-danger`, `alert-warning`, etc.) which already use the same semantic palette.

## Mandatory: verify every UI change in a real browser via chrome-devtools MCP

There is no test suite and no linter in this repo — a template/CSS/JS change that looks correct in the diff can still be broken at render time (wrong `url_for` path, a Jinja typo that silently renders blank, a JS selector that no longer matches). **Reading the source is not verification.** Before reporting any UI change as done:

1. Make sure the Flask dev server is running (`python app.py`) against the change.
2. Drive an actual browser with the `mcp__chrome-devtools__*` tools — don't skip this because the task didn't explicitly say "test in a browser":
   - `navigate_page` (via `new_page` if none is open) to the changed page at `http://127.0.0.1:5000/...`.
   - `list_console_messages` — this is the single highest-value check here, since a broken vendored-asset path (see above) or a JS error in a cloned-row handler fails **silently on screen** but always shows in the console.
   - `list_network_requests` — confirm every asset request (vendored Bootstrap CSS/JS, `style.css`, any new vendored library) returned 200, not 404. A typo'd `static/vendor/...` path is exactly the kind of regression that's invisible unless you check this.
   - `take_screenshot` — visually confirm spacing/layout/color match the conventions above, not just "the element exists."
   - For anything interactive (scan box, batch-select, add-row/remove-row, print button), actually exercise it with `click`/`fill`/`type_text`/`press_key` rather than assuming the markup is correct.
3. For a print-oriented page (invoices, barcode labels), also check the printable output itself — take a screenshot with print-affecting CSS in mind, and confirm `.no-print` elements are the only ones excluded, not the content that should print.

Skipping this step and reporting "done" from source-reading alone is not acceptable for any change that touches a template, `static/css/style.css`, or inline `<script>` — this app has no other safety net for frontend regressions.
