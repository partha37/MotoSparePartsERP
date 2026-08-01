---
name: new-form-checklist
description: The silent-failure traps for every new HTML form in MotoSparePartsERP — missing manual CSRF token, raw date strings hitting db.Date columns, and the id/for/aria-label baseline the searchable-select UI depends on. Use whenever adding or editing a template with a <form method="post">.
---

# New form checklist

Forms in this codebase are plain HTML + `request.form` — there is no Flask-WTF form class generating fields or tokens automatically. These mistakes cause failures that look unrelated to the actual cause, so check all of them on every new or edited form.

## 1. CSRF token — required on every single POST form, no exceptions

`CSRFProtect` is enabled globally in [extensions.py](../../../extensions.py), but nothing injects the token automatically. Every `<form method="post">` — including a bare delete button that's just one form in a list template — needs:

```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

Missing this causes a 400 on submit with no obvious link back to "forgot the hidden input." If a POST is mysteriously 400ing, check this first.

## 2. Date inputs need conversion before hitting a `db.Date` column

An HTML `<input type="date">` submits an ISO string (`"2026-08-01"`). Assigning that raw string to a `db.Date` column (`Purchase.date`, `Sale.date`, `StockMovement.date`, etc.) raises `TypeError` at insert/update time under SQLite. Convert first:

```python
from datetime import date
purchase.date = date.fromisoformat(request.form["date"])
```

**This conversion is only needed when assigning to the column.** Filtering/comparing an existing `Date` column against a plain ISO string in a `WHERE` clause (as `routes/stock.py` and `routes/reports.py` do for date-range filters) works fine as-is and must NOT be "fixed" with `fromisoformat` — that would break the comparison instead.

## 3. Every input/select needs an `id`, paired with its `<label for="...">`

This isn't just accessibility polish — [[ui-visual-conventions]]'s `SearchableSelect.enhance()` reads the `for` attribute to make clicking the label focus the proxy input it inserts in front of the now-hidden real `<select>`. A label without a matching `id`/`for` pair silently breaks "click label to focus" on any enhanced select, with no error to point at the cause. Give every field `id="f-something"` and its label `for="f-something"`; a field inside a repeated table row with no visible label (a bare Qty/Price cell) gets `aria-label="..."` on the input itself instead. Required fields also get `class="form-label required"` on the label (not `form-label` alone) so the asterisk marker renders — see [[ui-visual-conventions]].

## Quick self-check before shipping a new form

- [ ] Hidden CSRF input present, inside the `<form>` tag (including delete-button-only forms).
- [ ] Every date field assigned to a model column goes through `date.fromisoformat()`.
- [ ] Every date field only used in a filter/query stays a raw string.
- [ ] Every input/select has an `id`; every visible label has a matching `for`; label-less table-cell inputs have `aria-label`.
- [ ] Required fields' labels have the `required` class, not just the input's `required` attribute.
- [ ] Any new `<select>` gets `SearchableSelect.enhance()` in the page's script — see [[ui-visual-conventions]].
- [ ] If the form changes stock, see [[stock-mutation-checklist]].
