---
name: senior-architect-review
description: Senior-architect-level code review calibrated specifically to MotoSparePartsERP's tech stack and domain invariants — not generic best practices. Use before considering any change to this repo done, or whenever the user asks for a review, a second opinion, or "does this break anything."
---

# Senior architect review — MotoSparePartsERP

You are reviewing as a senior architect **who knows this exact codebase's stack and deliberate constraints**, not a generic reviewer applying best practices from a different kind of system. Most generic advice (add caching, add a queue, split into microservices, add TypeScript, containerize it) is actively wrong here — flag it as a mistake, not a missed opportunity, if you see it suggested.

## The tech stack (know this before reviewing anything)

- **Runtime**: Python 3.11, Flask, single process, run with `python app.py`, no WSGI server, no reverse proxy.
- **Structure**: app-factory pattern — `create_app()` in `app.py` wires up `db`/`migrate`/`login_manager`/`csrf` from `extensions.py` and registers one blueprint per domain from `routes/` (auth, dashboard, products, suppliers, purchases, customers, mechanics, sales, stock, reports, settings). Each blueprint owns its templates under `templates/<blueprint>/`.
- **Data layer**: one `models.py` for every table — no per-domain model files, no repository/service layer, no ORM abstraction beyond plain SQLAlchemy models. SQLite, single file at `instance/erp.db`, gitignored. Flask-Migrate/Alembic for schema changes.
- **Frontend**: server-rendered Jinja2 + Bootstrap 5. **No JS build step, no bundler, no npm, no SPA framework.** Any inline `<script>` in a template is the entire frontend toolchain — that is intentional, not a gap to fill. There is a small custom design system on top of stock Bootstrap: brand-color CSS-variable overrides, an `icon()` Jinja helper inlining vendored SVGs, and a global `SearchableSelect` combobox helper that every `<select>` goes through — see [[ui-visual-conventions]] for the rules (enhance/reset/refreshSearchable) that any UI-touching diff must follow. `base.html` also has a document-level "Enter advances to next field" handler — anything that wants to handle Enter itself (e.g. a future barcode scan box) must `stopPropagation()` or it'll conflict with that.
- **Forms**: plain HTML + `request.form`, not Flask-WTF form classes. `CSRFProtect` is global but does not auto-inject tokens — every POST form needs a manual hidden `csrf_token` input.
- **Auth**: Flask-Login, exactly one user account (shop owner), no roles, no multi-tenancy.
- **Deployment model**: offline-first, single shop, single user, no cloud hosting, no Docker. The counter must keep working with no internet connection. This is a hard constraint, not a v1-only shortcut — do not flag "no cloud backup" or "no internet dependency handling" as a gap.
- **No test suite, no linter, no CI configured** — this is a known, accepted state for a beginner-coder-maintained single-shop tool, not something to flag as a finding on every review. Only flag it if the specific change you're reviewing is complex/risky enough that its absence materially increases the chance of a shipped bug.
- **Excel mirror**: `excel_sync.py::sync_to_excel()` rewrites `instance/erp_data.xlsx` from the DB and must run after every mutating commit. CSV export is separately hand-mapped in `routes/settings.py`.

Judge every review finding against this stack, not against what a general SaaS backend "should" look like. A missing Redis cache is not a finding. A missing `StockMovement` row is.

## Domain invariants to check on every relevant diff

Pull in the matching project skill for full detail on each — don't just pattern-match against this summary:

1. **Stock changes** — any route creating/editing/deleting a Purchase, Sale, or stock adjustment must update `Product.current_stock`, insert a signed `StockMovement` row, and call `sync_to_excel()`. See [[stock-mutation-checklist]].
2. **New/changed forms** — manual CSRF hidden input present; date inputs converted with `date.fromisoformat()` before assignment to a `db.Date` column (but NOT when used in a filter/WHERE comparison against a raw ISO string — that's correct as-is). See [[new-form-checklist]].
3. **Model changes** — migration generated AND hand-checked (SQLite autogenerate is not fully reliable), nullable-unique used correctly for optional-but-unique fields, computed fields like `recalc_prices()` called explicitly wherever `mrp`/`actual_discount_pct` change. See [[add-database-field]].
4. **New exportable data** — new/changed models wired into `EXPORTABLE` (`routes/settings.py`) and `SHEETS` (`excel_sync.py`), with the row's own attribute checked before falling back to `_DERIVED`. See [[add-exportable-table]].
5. **Batch/FIFO correctness** (`PurchaseItem.remaining_qty`, `mrp_at_purchase`, `stock_number`, `effective_mrp`): a sale must decrement the *specific* batch referenced by `purchase_item_id`, never borrow across batches silently, and must reject the whole sale (not partially fulfill) if that batch lacks enough `remaining_qty`. Legacy rows predating batch tracking have `mrp_at_purchase = None` and sale rows may have `purchase_item_id = None` — any new code touching these paths must handle that fallback (`effective_mrp` pattern), not assume every row is fully populated.
6. **Pricing/GST rules** — MRP is GST-inclusive; `SaleItem.line_total` and `Sale.total` must never add GST on top. `Customer.discount_pct` is a client-side-only convenience (pre-fills the form) and is deliberately NOT enforced server-side — `routes/sales.py` accepting any submitted `selling_price` is correct behavior, not a missing validation, unless the user explicitly asks to change that policy.
7. **Deletion guards** — Products/Suppliers/Customers/Mechanics referenced by any Purchase/Sale line item must be blocked from deletion at the application layer with a flashed error (SQLite FK enforcement is off here, so this can't be delegated to the DB).
8. **Invoice numbering** — `Sale.invoice_no` must go through `routes/sales.py::_next_invoice_no()`, not be hand-rolled elsewhere, to avoid collisions/gaps.
9. **UI component conventions** — new `<select>` elements go through `SearchableSelect.enhance()`, cloned rows call `SearchableSelect.reset()` before re-enhancing, programmatic value changes call `.refreshSearchable()` afterward, new icons reference an actually-vendored SVG in `static/vendor/bootstrap-icons/`, and no hardcoded hex colors bypass the `--brand`/`--accent` CSS variables. See [[ui-visual-conventions]] for the full rules — a diff that reinvents any of these instead of reusing them is a finding.
10. **Concurrency reality check** — this is a single-process, single-user, single-machine app. Do not flag missing distributed locks, missing optimistic concurrency control, or race conditions between "concurrent users" as findings — there is exactly one user. Do flag genuine same-request logic bugs (e.g. reading `remaining_qty` twice and computing from a stale value within one request).

## Review process

1. Read the actual diff (`git diff`, or the specific files named), not just the task description — verify claims against real code, don't assume a pattern held from a prior review.
2. Walk the changed files against the invariants above, and against any other project skill relevant to what changed.
3. For anything you're not sure is actually broken, read enough surrounding code to confirm before flagging it — don't report a "maybe."
4. **If any changed file is a template, `static/css/style.css`, or inline `<script>`, source-reading is not sufficient** — run the chrome-devtools MCP verification in [[ui-visual-conventions]] (console messages, network requests, screenshot, and exercising any interactive element) before clearing the change. A template diff that "looks right" can still 404 an asset or throw a JS error at render time; this review isn't done until that's been checked in a real browser, not just read.
5. Rank findings most-severe first: correctness/data-integrity bugs (wrong stock count, silent cross-batch borrow, missing CSRF token causing a 400, GST double-counting) outrank style or structure comments.
6. Do not suggest architecture changes that fight the stack (splitting into services, adding a task queue, introducing an ORM abstraction layer, adding a JS framework) — this is a deliberately minimal, single-shop, offline tool.
7. If the review tool context calls for it, report via the `ReportFindings` tool; otherwise give a direct, concrete list — file, line, concrete failure scenario, not vague warnings.
