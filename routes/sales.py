from datetime import date, datetime
from urllib.parse import urlencode

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func

from extensions import db
from excel_sync import sync_to_excel
from models import (
    Sale, SaleItem, Payment, Product, PurchaseItem, Customer, Mechanic, StockMovement,
    ShopSettings, SaleReturn, SaleReturnItem,
)
from routes.server_table import ServerTable, date_filter_expr

sales_bp = Blueprint("sales", __name__, url_prefix="/sales")


def _next_invoice_no():
    last = Sale.query.order_by(Sale.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"INV-{next_id:05d}"


def _attach_available_batches(products):
    """For each product, attach `.available_batches` — its sellable stock batches
    (oldest purchase first), so the sales form can offer a specific batch/MRP to sell from."""
    for product in products:
        batches = [b for b in product.purchase_items if (b.remaining_qty or 0) > 0]
        batches.sort(key=lambda b: (b.purchase.date, b.id))
        product.available_batches = [
            {
                "id": b.id,
                "label": f"{b.stock_number} — {b.remaining_qty} left — MRP ₹{b.effective_mrp:.2f}",
                "price": b.effective_mrp,
                "stock": b.remaining_qty,
            }
            for b in batches
        ]
    return products


def _attach_discount_maps(owners):
    """Attach `.brand_discount_map` ({brand_id: pct}) and `.category_discount_map`
    ({"brand_id:category_id": pct}) to each Customer/Mechanic, so the sales form can
    look up the right rate per product line client-side. A line uses the second map
    when the product's brand+category pair is in it, and the first map otherwise —
    same precedence as Customer/Mechanic.discount_for_product(). The composite key
    is a string because these maps cross into JS as JSON, where keys are strings."""
    for owner in owners:
        owner.brand_discount_map = {bd.brand_id: bd.discount_pct or 0 for bd in owner.brand_discounts}
        owner.category_discount_map = {
            f"{cd.brand_id}:{cd.category_id}": cd.discount_pct or 0 for cd in owner.category_discounts
        }
    return owners


def _validate_sale_form(form, editing_sale=None):
    """Parses+validates the New/Edit Sale form. Returns (errors, parsed) —
    on any error, `parsed` is None and the caller should flash each error and
    re-render the form; on success, `errors` is empty and `parsed` holds
    everything needed to build/update a Sale (batches already resolved to
    PurchaseItem rows, so the caller never re-queries them).

    `editing_sale`, when given, is the Sale being edited — its own line
    items haven't been reversed yet at validation time (that only happens
    after validation succeeds, see edit_sale), so a batch this sale already
    drew from would otherwise look short on stock even when the edited
    qty is unchanged or lower. Availability is checked against
    remaining_qty *plus* whatever this same sale currently holds from that
    batch, so re-submitting the same (or a smaller) qty against an
    already-fully-drawn batch validates correctly."""
    already_held = {}
    if editing_sale:
        for item in editing_sale.items:
            if item.purchase_item_id:
                already_held[item.purchase_item_id] = already_held.get(item.purchase_item_id, 0) + item.qty

    sale_date = date.fromisoformat(form.get("date") or date.today().isoformat())
    customer_raw = form.get("customer_id", "")
    is_walkin = customer_raw == "walkin"
    customer_id = None if is_walkin else (customer_raw or None)
    mechanic_id = form.get("mechanic_id") or None
    payment_mode = form.get("payment_mode", "cash")
    amount_paid = float(form.get("amount_paid") or 0)

    product_ids = form.getlist("product_filter[]")
    batch_ids = form.getlist("purchase_item_id[]")
    qtys = form.getlist("qty[]")
    prices = form.getlist("selling_price[]")

    raw_rows = list(zip(product_ids, batch_ids, qtys, prices))
    raw_valid_rows = [(bid, qty, price) for pid, bid, qty, price in raw_rows if bid and qty and price]
    # Qty is excluded from the "did the user touch this row" check: a fresh
    # blank row's qty always defaults to 1 client-side (see addBlankRow in
    # sales/form.html), so its presence alone doesn't indicate real intent —
    # only a picked product/batch or a typed price does.
    partial_rows = [
        pid for pid, bid, qty, price in raw_rows
        if (pid or bid or price) and not (bid and qty and price)
    ]

    errors = []

    # A sale is billed to exactly one of Mechanic or Customer — "Walk-in"
    # counts as a customer choice here (it's a real, deliberate answer to
    # "who's this for"), but the "-- None --" placeholder does not. The
    # form's own JS already locks each field once the other has a value,
    # but that's client-side only, so it's re-checked here too.
    mechanic_chosen = bool(mechanic_id)
    customer_chosen = is_walkin or bool(customer_id)
    if mechanic_chosen and customer_chosen:
        errors.append("Choose either a Mechanic or a Customer, not both.")
    elif not mechanic_chosen and not customer_chosen:
        errors.append("Choose a Mechanic or a Customer before saving the sale.")

    if not raw_valid_rows:
        errors.append("Add at least one product to the sale.")

    if partial_rows:
        errors.append("Some lines have a product/batch selected but are missing Qty or Price — fill them in or remove the line.")

    rows = []
    if not errors:
        # Validate batch availability before committing anything.
        shortages = []
        for bid, qty, price in raw_valid_rows:
            batch = PurchaseItem.query.get(int(bid))
            qty = int(qty)
            if not batch:
                shortages.append("Selected stock batch no longer exists — please re-pick it.")
                continue
            effective_remaining = (batch.remaining_qty or 0) + already_held.get(batch.id, 0)
            if qty > effective_remaining:
                shortages.append(
                    f"{batch.product.product_name} ({batch.stock_number}): "
                    f"have {effective_remaining}, need {qty}"
                )
                continue
            rows.append((batch, qty, float(price)))

        if shortages:
            errors.append("Not enough stock for: " + ", ".join(shortages))

    if errors:
        return errors, None

    return [], {
        "sale_date": sale_date,
        "customer_id": customer_id,
        "mechanic_id": mechanic_id,
        "payment_mode": payment_mode,
        "is_walkin": is_walkin,
        "amount_paid": amount_paid,
        "rows": rows,
    }


def _reverse_sale_side_effects(sale):
    """Undoes this sale's stock/StockMovement/Payment footprint before
    re-applying edited data — restores each batch's remaining_qty and the
    product's current_stock, deletes the old StockMovement rows (found by
    reference, since StockMovement has no FK/relationship), then deletes the
    old SaleItem rows and the single checkout-time Payment (if any). Does not
    commit — the caller commits once, after re-applying the new data, so the
    whole edit is one transaction. Only ever called from edit_sale, which has
    already confirmed via Sale.is_editable that there's at most one Payment
    and no return referencing this sale."""
    for item in list(sale.items):
        if item.purchase_item:
            item.purchase_item.remaining_qty = (item.purchase_item.remaining_qty or 0) + item.qty
        if item.product:
            item.product.current_stock = (item.product.current_stock or 0) + item.qty
        db.session.delete(item)
    StockMovement.query.filter_by(reference_type="sale", reference_id=sale.id).delete()
    for payment in list(sale.payments):
        db.session.delete(payment)


@sales_bp.route("/")
@login_required
def list_sales():
    item_totals = (
        db.session.query(
            SaleItem.sale_id.label("sale_id"),
            func.sum(SaleItem.qty * SaleItem.selling_price).label("total"),
        )
        .group_by(SaleItem.sale_id)
        .subquery()
    )
    paid_totals = (
        db.session.query(
            Payment.sale_id.label("sale_id"),
            func.sum(Payment.amount).label("paid"),
        )
        .group_by(Payment.sale_id)
        .subquery()
    )
    # A return's credit counts toward whichever sale it was applied to — the
    # original sale it was returned against, unless the exchange flow applied
    # it to a different, newly-created sale instead (SaleReturn.applied_to_sale_id).
    return_item_totals = (
        db.session.query(
            SaleReturnItem.sale_return_id.label("sale_return_id"),
            func.sum(SaleReturnItem.qty * SaleItem.selling_price).label("amount"),
        )
        .join(SaleItem, SaleReturnItem.sale_item_id == SaleItem.id)
        .group_by(SaleReturnItem.sale_return_id)
        .subquery()
    )
    return_totals = (
        db.session.query(
            func.coalesce(SaleReturn.applied_to_sale_id, SaleReturn.sale_id).label("sale_id"),
            func.sum(return_item_totals.c.amount).label("return_credit"),
        )
        .join(return_item_totals, SaleReturn.id == return_item_totals.c.sale_return_id)
        .group_by(func.coalesce(SaleReturn.applied_to_sale_id, SaleReturn.sale_id))
        .subquery()
    )
    total_expr = func.coalesce(item_totals.c.total, 0.0)
    balance_expr = (
        total_expr
        - func.coalesce(paid_totals.c.paid, 0.0)
        - func.coalesce(return_totals.c.return_credit, 0.0)
    )

    query = (
        Sale.query
        .outerjoin(item_totals, Sale.id == item_totals.c.sale_id)
        .outerjoin(paid_totals, Sale.id == paid_totals.c.sale_id)
        .outerjoin(return_totals, Sale.id == return_totals.c.sale_id)
        .outerjoin(Customer, Sale.customer_id == Customer.id)
        .outerjoin(Mechanic, Sale.mechanic_id == Mechanic.id)
    )

    columns = {
        "date": ("Date", Sale.date, date_filter_expr(Sale.date)),
        "invoice": ("Invoice", Sale.invoice_no),
        "customer": ("Customer", Customer.name),
        "mechanic": ("Mechanic", Mechanic.name),
        "total": ("Total", total_expr),
        "balance": ("Balance Due", balance_expr),
    }
    table = ServerTable(
        query, columns,
        search_keys=["date", "invoice", "customer", "mechanic", "total", "balance"],
        default_sort="date", default_dir="desc",
    )
    return render_template("sales/list.html", table=table)


@sales_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_sale():
    products = _attach_available_batches(Product.query.order_by(Product.product_name.asc()).all())
    customers = _attach_discount_maps(Customer.query.order_by(Customer.name.asc()).all())
    mechanics = _attach_discount_maps(Mechanic.query.order_by(Mechanic.name.asc()).all())

    if request.method == "POST":
        errors, parsed = _validate_sale_form(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "sales/form.html", products=products, customers=customers,
                mechanics=mechanics, today=date.today().isoformat()
            )

        sale = Sale(
            invoice_no=_next_invoice_no(),
            date=parsed["sale_date"],
            customer_id=int(parsed["customer_id"]) if parsed["customer_id"] else None,
            mechanic_id=int(parsed["mechanic_id"]) if parsed["mechanic_id"] else None,
            payment_mode=parsed["payment_mode"],
            is_walkin=parsed["is_walkin"],
        )
        db.session.add(sale)
        db.session.flush()

        if parsed["amount_paid"] > 0:
            db.session.add(
                Payment(
                    sale_id=sale.id,
                    date=parsed["sale_date"],
                    amount=parsed["amount_paid"],
                    payment_mode=parsed["payment_mode"],
                    note="Payment at sale",
                )
            )

        for batch, qty, price in parsed["rows"]:
            product = batch.product

            db.session.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    qty=qty,
                    selling_price=price,
                    purchase_item_id=batch.id,
                )
            )

            batch.remaining_qty = (batch.remaining_qty or 0) - qty
            product.current_stock = (product.current_stock or 0) - qty

            db.session.add(
                StockMovement(
                    product_id=product.id,
                    date=parsed["sale_date"],
                    type="sale_out",
                    qty=-qty,
                    reference_type="sale",
                    reference_id=sale.id,
                    note=f"Sale {sale.invoice_no} (batch {batch.stock_number})",
                )
            )

        db.session.commit()
        sync_to_excel()
        flash("Sale recorded and stock updated.", "success")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    return render_template(
        "sales/form.html", products=products, customers=customers,
        mechanics=mechanics, today=date.today().isoformat()
    )


@sales_bp.route("/<int:sale_id>/edit", methods=["GET", "POST"])
@login_required
def edit_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    if not sale.is_editable:
        flash("This sale can no longer be edited.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    products = _attach_available_batches(Product.query.order_by(Product.product_name.asc()).all())
    customers = _attach_discount_maps(Customer.query.order_by(Customer.name.asc()).all())
    mechanics = _attach_discount_maps(Mechanic.query.order_by(Mechanic.name.asc()).all())

    if request.method == "POST":
        if not sale.is_editable:  # re-check in case something changed since the GET
            flash("This sale can no longer be edited.", "danger")
            return redirect(url_for("sales.view_sale", sale_id=sale.id))

        errors, parsed = _validate_sale_form(request.form, editing_sale=sale)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "sales/form.html", sale=sale, products=products, customers=customers,
                mechanics=mechanics, today=sale.date.isoformat()
            )

        _reverse_sale_side_effects(sale)

        sale.date = parsed["sale_date"]
        sale.customer_id = int(parsed["customer_id"]) if parsed["customer_id"] else None
        sale.mechanic_id = int(parsed["mechanic_id"]) if parsed["mechanic_id"] else None
        sale.payment_mode = parsed["payment_mode"]
        sale.is_walkin = parsed["is_walkin"]
        # invoice_no / id / created_at are never touched by an edit

        if parsed["amount_paid"] > 0:
            db.session.add(
                Payment(
                    sale_id=sale.id,
                    date=sale.date,
                    amount=parsed["amount_paid"],
                    payment_mode=sale.payment_mode,
                    note="Payment at sale",
                )
            )

        for batch, qty, price in parsed["rows"]:
            product = batch.product

            db.session.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    qty=qty,
                    selling_price=price,
                    purchase_item_id=batch.id,
                )
            )

            batch.remaining_qty = (batch.remaining_qty or 0) - qty
            product.current_stock = (product.current_stock or 0) - qty

            db.session.add(
                StockMovement(
                    product_id=product.id,
                    date=sale.date,
                    type="sale_out",
                    qty=-qty,
                    reference_type="sale",
                    reference_id=sale.id,
                    note=f"Sale {sale.invoice_no} (batch {batch.stock_number})",
                )
            )

        db.session.commit()
        sync_to_excel()
        flash("Sale updated.", "success")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    return render_template(
        "sales/form.html", sale=sale, products=products, customers=customers,
        mechanics=mechanics, today=sale.date.isoformat()
    )


@sales_bp.route("/<int:sale_id>")
@login_required
def view_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    shop = ShopSettings.query.first() or ShopSettings()
    return render_template(
        "sales/view.html", sale=sale, shop=shop, today=date.today().isoformat()
    )


def bill_rounding(total):
    """Whole-rupee grand total plus the rounding delta printed above it."""
    rounded = round(total)
    return rounded, round(rounded - total, 2)


def gst_label(rate):
    """The per-line tax column. Display only — nothing on the sales side adds
    GST on top, since MRP already includes it (see CLAUDE.md)."""
    return f"{int(round(rate))}%" if rate else "Exempt"


def bill_size(args):
    return "a4" if args.get("size") == "a4" else "80mm"


@sales_bp.route("/<int:sale_id>/bill")
@login_required
def bill(sale_id):
    """The printable customer bill. 80mm thermal roll is the counter default;
    ?size=a4 renders the same figures as a full-width sheet instead."""
    sale = Sale.query.get_or_404(sale_id)
    shop = ShopSettings.query.first() or ShopSettings()
    # Totalling MRP here rather than on the model: it's only ever the printed
    # bill's "you saved this much" line, not something the rest of the app bills on.
    mrp_total = round(sum(item.mrp_at_sale * item.qty for item in sale.items), 2)
    rounded_total, round_off = bill_rounding(sale.total)

    extra_rows = []
    discount = round(mrp_total - sale.total, 2)
    if discount > 0:
        extra_rows.append(("Discount Amt", discount))
    if sale.return_credit > 0:
        extra_rows.append(("Less : Returns", sale.return_credit))
    if sale.balance_due != 0:
        extra_rows.append(("Amount Paid", sale.amount_paid))
        extra_rows.append((
            "Refund Due" if sale.balance_due < 0 else "Balance Due", abs(sale.balance_due),
        ))

    return render_template(
        "sales/bill.html",
        shop=shop,
        size=bill_size(request.args),
        bill={
            "title": "TAX INVOICE",
            "no_label": "Invoice No/Date",
            "no": sale.invoice_no,
            "date": sale.date,
            "created_at": sale.created_at,
            "customer_name": sale.customer_display,
            "customer_mobile": sale.customer.phone if sale.customer else "",
            "mechanic": sale.mechanic.name if sale.mechanic else "",
            "payment_mode": sale.payment_mode,
            "show_part_no": True,
            "lines": [
                {
                    "name": item.product.product_name,
                    "part_no": item.product.part_no,
                    "gst": gst_label(item.product.gst_rate),
                    "mrp": item.mrp_at_sale,
                    "rate": item.selling_price,
                    "qty": item.qty,
                    "amount": item.line_total,
                }
                for item in sale.items
            ],
            "total_label": "Total",
            "total": sale.total,
            "round_off": round_off,
            "rounded_total": rounded_total,
            "grand_label": "TOTAL Rs.",
            "extra_rows": extra_rows,
            "thanks": "THANK YOU VISIT AGAIN",
            "self_url": url_for("sales.bill", sale_id=sale.id),
            "self_url_a4": url_for("sales.bill", sale_id=sale.id, size="a4"),
            "back_url": url_for("sales.view_sale", sale_id=sale.id),
            "back_label": "Back to Sale",
        },
    )


def _num(raw, default=0.0):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


@sales_bp.route("/quick-bill")
@login_required
def quick_bill():
    """Form for a one-off printed bill that isn't a Sale — for reprinting a
    sample, or billing something outside the catalogue. Nothing here is
    saved: no Sale row, no stock movement, no invoice number consumed."""
    return render_template(
        "sales/quick_bill.html",
        today=date.today().isoformat(),
        default_no="QB-" + date.today().strftime("%d%m%Y"),
    )


@sales_bp.route("/quick-bill/print")
@login_required
def quick_bill_print():
    """Renders the typed-in lines through the same bill layout as a real sale.
    Deliberately a GET off the query string — it reads nothing and writes
    nothing, so reloading it or switching paper size just re-renders."""
    shop = ShopSettings.query.first() or ShopSettings()

    lines = []
    fields = (
        request.args.getlist("name[]"),
        request.args.getlist("gst[]"),
        request.args.getlist("mrp[]"),
        request.args.getlist("rate[]"),
        request.args.getlist("qty[]"),
    )
    for name, gst, mrp, rate, qty in zip(*fields):
        if not name.strip():
            continue
        rate_val = _num(rate)
        qty_val = int(_num(qty, 1)) or 1
        lines.append({
            "name": name.strip(),
            "part_no": "",
            # Blank GST means the line is untaxed, same as a product with no rate.
            "gst": gst_label(_num(gst)),
            "mrp": _num(mrp) or rate_val,
            "rate": rate_val,
            "qty": qty_val,
            "amount": round(rate_val * qty_val, 2),
        })

    total = round(sum(line["amount"] for line in lines), 2)
    mrp_total = round(sum(line["mrp"] * line["qty"] for line in lines), 2)
    rounded_total, round_off = bill_rounding(total)

    extra_rows = []
    discount = round(mrp_total - total, 2)
    if discount > 0:
        extra_rows.append(("Discount Amt", discount))
    paid_raw = request.args.get("amount_paid", "").strip()
    if paid_raw:
        paid = _num(paid_raw)
        extra_rows.append(("Amount Paid", paid))
        extra_rows.append(("Balance Due", round(rounded_total - paid, 2)))

    # Keep every field except the ones the toolbar itself sets, so the paper-size
    # links re-render the very same bill rather than an empty one.
    carried = [(k, v) for k, v in request.args.items(multi=True) if k not in ("size", "auto")]
    base = url_for("sales.quick_bill_print")

    bill_date = request.args.get("date") or date.today().isoformat()
    return render_template(
        "sales/bill.html",
        shop=shop,
        size=bill_size(request.args),
        bill={
            "title": request.args.get("title", "").strip() or "TAX INVOICE",
            "no_label": "Bill No/Date",
            "no": request.args.get("bill_no", "").strip(),
            "date": date.fromisoformat(bill_date),
            "created_at": datetime.utcnow(),
            "customer_name": request.args.get("customer_name", "").strip() or "-",
            "customer_mobile": request.args.get("customer_mobile", "").strip(),
            "mechanic": "",
            "payment_mode": request.args.get("payment_mode", "").strip(),
            "show_part_no": False,
            "lines": lines,
            "total_label": "Total",
            "total": total,
            "round_off": round_off,
            "rounded_total": rounded_total,
            "grand_label": "TOTAL Rs.",
            "extra_rows": extra_rows,
            "thanks": "THANK YOU VISIT AGAIN",
            "self_url": base + "?" + urlencode(carried),
            "self_url_a4": base + "?" + urlencode(carried + [("size", "a4")]),
            "back_url": url_for("sales.quick_bill") + "?" + urlencode(carried),
            "back_label": "Edit Bill",
        },
    )


@sales_bp.route("/<int:sale_id>/record-payment", methods=["POST"])
@login_required
def record_payment(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    payment_date = date.fromisoformat(request.form.get("date") or date.today().isoformat())
    amount = float(request.form.get("amount") or 0)
    payment_mode = request.form.get("payment_mode", "cash")
    note = request.form.get("note", "").strip()

    if amount <= 0:
        flash("Enter a payment amount greater than zero.", "danger")
    elif amount > sale.balance_due + 0.01:
        flash(
            f"Payment of ₹{amount:.2f} exceeds the balance due of ₹{sale.balance_due:.2f}.",
            "danger",
        )
    else:
        db.session.add(
            Payment(
                sale_id=sale.id,
                date=payment_date,
                amount=amount,
                payment_mode=payment_mode,
                note=note,
            )
        )
        db.session.commit()
        sync_to_excel()
        flash("Payment recorded.", "success")

    return redirect(url_for("sales.view_sale", sale_id=sale.id))


@sales_bp.route("/payments/<int:payment_id>/delete", methods=["POST"])
@login_required
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    sale_id = payment.sale_id
    db.session.delete(payment)
    db.session.commit()
    sync_to_excel()
    flash("Payment removed.", "success")
    return redirect(url_for("sales.view_sale", sale_id=sale_id))


@sales_bp.route("/<int:sale_id>/record-refund", methods=["POST"])
@login_required
def record_refund(sale_id):
    """Logs actual cash handed back to the customer against a return credit —
    stored as a negative-amount Payment (Sale.amount_paid is already a
    sign-agnostic sum, so this needs no other code changes to settle back to
    balance_due == 0). Purely a money record — the stock side of a return is
    already handled when the SaleReturn itself was created."""
    sale = Sale.query.get_or_404(sale_id)
    refund_date = date.fromisoformat(request.form.get("date") or date.today().isoformat())
    amount = float(request.form.get("amount") or 0)
    payment_mode = request.form.get("payment_mode", "cash")
    note = request.form.get("note", "").strip()

    refund_owed = max(0, -sale.balance_due)
    if amount <= 0:
        flash("Enter a refund amount greater than zero.", "danger")
    elif amount > refund_owed + 0.01:
        flash(
            f"Refund of ₹{amount:.2f} exceeds the ₹{refund_owed:.2f} owed back to the customer.",
            "danger",
        )
    else:
        db.session.add(
            Payment(
                sale_id=sale.id,
                date=refund_date,
                amount=-amount,
                payment_mode=payment_mode,
                note=note or "Refund paid to customer",
            )
        )
        db.session.commit()
        sync_to_excel()
        flash("Refund recorded.", "success")

    return redirect(url_for("sales.view_sale", sale_id=sale.id))
