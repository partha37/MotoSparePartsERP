from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from extensions import db
from excel_sync import sync_to_excel
from models import (
    Sale, SaleItem, SaleReturn, SaleReturnItem, Product, PurchaseItem,
    Customer, Mechanic, StockMovement,
)
from routes.sales import _attach_available_batches, _attach_discount_maps, _next_invoice_no

sale_returns_bp = Blueprint("sale_returns", __name__, url_prefix="/sales/<int:sale_id>/returns")

CONDITIONS = ("resellable", "defective")


def _next_return_no():
    last = SaleReturn.query.order_by(SaleReturn.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"RET-{next_id:05d}"


def _parse_return_rows(sale, form):
    """Parses & validates the return lines submitted for `sale` (one
    qty[]/condition[] pair per sale.items, in the same order they were
    rendered). Returns (rows, errors) — rows is a list of
    (sale_item, qty, condition) for lines with qty > 0; errors is a list of
    human-readable strings. Nothing is written to the DB here."""
    sale_item_ids = form.getlist("sale_item_id[]")
    qtys = form.getlist("qty[]")
    conditions = form.getlist("condition[]")

    errors = []
    rows = []
    for sid, qty_raw, condition in zip(sale_item_ids, qtys, conditions):
        qty = int(qty_raw) if (qty_raw or "").strip().isdigit() else 0
        if qty <= 0:
            continue
        sale_item = SaleItem.query.get(int(sid)) if sid else None
        if not sale_item or sale_item.sale_id != sale.id:
            errors.append("Selected item no longer belongs to this sale — please re-check the form.")
            continue
        if condition not in CONDITIONS:
            errors.append(f"{sale_item.product.product_name}: pick a condition (resellable or defective).")
            continue
        if qty > sale_item.returnable_qty:
            errors.append(
                f"{sale_item.product.product_name}: only {sale_item.returnable_qty} left returnable, requested {qty}."
            )
            continue
        rows.append((sale_item, qty, condition))

    if not rows and not errors:
        errors.append("Select at least one item and quantity to return.")

    return rows, errors


def _create_return(sale, rows, return_date, note, applied_to_sale_id=None):
    """Creates the SaleReturn + SaleReturnItems for already-validated `rows`
    and runs the resellable-only 3-step stock mutation. Does not commit —
    caller controls the transaction (the plain-return route commits
    immediately after; the exchange route commits once alongside the new
    sale it creates in the same request)."""
    sale_return = SaleReturn(
        sale_id=sale.id,
        applied_to_sale_id=applied_to_sale_id,
        return_no=_next_return_no(),
        date=return_date,
        note=note,
    )
    db.session.add(sale_return)
    db.session.flush()

    for sale_item, qty, condition in rows:
        db.session.add(
            SaleReturnItem(
                sale_return_id=sale_return.id,
                sale_item_id=sale_item.id,
                qty=qty,
                condition=condition,
            )
        )

        if condition == "resellable":
            product = sale_item.product
            product.current_stock = (product.current_stock or 0) + qty

            note_suffix = ""
            if sale_item.purchase_item:
                sale_item.purchase_item.remaining_qty = (sale_item.purchase_item.remaining_qty or 0) + qty
            else:
                note_suffix = " (no batch on original sale)"

            db.session.add(
                StockMovement(
                    product_id=product.id,
                    date=return_date,
                    type="return",
                    qty=qty,
                    reference_type="sale_return",
                    reference_id=sale_return.id,
                    note=f"Return {sale_return.return_no} against {sale.invoice_no}{note_suffix}",
                )
            )

    return sale_return


@sale_returns_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_return(sale_id):
    sale = Sale.query.get_or_404(sale_id)

    if request.method == "POST":
        rows, errors = _parse_return_rows(sale, request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("sale_returns/new.html", sale=sale, today=date.today().isoformat())

        return_date = date.fromisoformat(request.form.get("date") or date.today().isoformat())
        note = request.form.get("note", "").strip()

        sale_return = _create_return(sale, rows, return_date, note)
        db.session.commit()
        sync_to_excel()
        flash(f"Return {sale_return.return_no} recorded.", "success")
        return redirect(url_for("sale_returns.view_return", sale_id=sale.id, return_id=sale_return.id))

    if not any(item.returnable_qty > 0 for item in sale.items):
        flash("Nothing left to return on this sale.", "warning")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    return render_template("sale_returns/new.html", sale=sale, today=date.today().isoformat())


@sale_returns_bp.route("/<int:return_id>")
@login_required
def view_return(sale_id, return_id):
    sale_return = SaleReturn.query.get_or_404(return_id)
    if sale_return.sale_id != sale_id:
        flash("Return not found for this sale.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale_id))
    return render_template("sale_returns/view.html", sale_return=sale_return, sale=sale_return.sale)


@sale_returns_bp.route("/exchange", methods=["GET", "POST"])
@login_required
def new_exchange(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    products = _attach_available_batches(Product.query.order_by(Product.product_name.asc()).all())
    customers = _attach_discount_maps(Customer.query.order_by(Customer.name.asc()).all())
    mechanics = _attach_discount_maps(Mechanic.query.order_by(Mechanic.name.asc()).all())

    def _rerender():
        return render_template(
            "sale_returns/exchange.html", sale=sale, products=products,
            customers=customers, mechanics=mechanics, today=date.today().isoformat(),
        )

    if request.method == "POST":
        return_rows, errors = _parse_return_rows(sale, request.form)

        exchange_date = date.fromisoformat(request.form.get("date") or date.today().isoformat())
        customer_raw = request.form.get("customer_id", "")
        if customer_raw == "walkin":
            customer_id, is_walkin = None, True
        elif customer_raw:
            customer_id, is_walkin = customer_raw, False
        else:
            # No selection submitted — fall back to the original sale's
            # customer/walk-in state, same as the mechanic_id fallback below.
            customer_id = sale.customer_id
            is_walkin = sale.is_walkin if not sale.customer_id else False
        mechanic_id = request.form.get("mechanic_id") or (sale.mechanic_id or None)

        # A sale is billed to exactly one of Mechanic or Customer — see the
        # matching check in routes/sales.py::new_sale for the reasoning.
        mechanic_chosen = bool(mechanic_id)
        customer_chosen = is_walkin or bool(customer_id)
        if mechanic_chosen and customer_chosen:
            errors.append("Choose either a Mechanic or a Customer, not both.")
        elif not mechanic_chosen and not customer_chosen:
            errors.append("Choose a Mechanic or a Customer before saving.")

        product_ids = request.form.getlist("product_filter[]")
        batch_ids = request.form.getlist("purchase_item_id[]")
        qtys = request.form.getlist("qty_sell[]")
        prices = request.form.getlist("selling_price[]")

        raw_sale_rows = list(zip(product_ids, batch_ids, qtys, prices))
        sale_rows = [(bid, qty, price) for pid, bid, qty, price in raw_sale_rows if bid and qty and price]
        partial_rows = [
            pid for pid, bid, qty, price in raw_sale_rows
            if (pid or bid or price) and not (bid and qty and price)
        ]
        if partial_rows:
            errors.append("Some new-sale lines have a product/batch selected but are missing Qty or Price.")

        shortages = []
        for bid, qty, _price in sale_rows:
            batch = PurchaseItem.query.get(int(bid))
            qty = int(qty)
            if not batch:
                shortages.append("Selected stock batch no longer exists — please re-pick it.")
            elif qty > (batch.remaining_qty or 0):
                shortages.append(
                    f"{batch.product.product_name} ({batch.stock_number}): have {batch.remaining_qty}, need {qty}"
                )
        if shortages:
            errors.append("Not enough stock for: " + ", ".join(shortages))

        if not return_rows and not sale_rows:
            errors.append("Add at least one item to return or to sell.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return _rerender()

        payment_mode = request.form.get("payment_mode", "cash")
        note = request.form.get("note", "").strip()

        exchange_sale = Sale(
            invoice_no=_next_invoice_no(),
            date=exchange_date,
            customer_id=int(customer_id) if customer_id else None,
            mechanic_id=int(mechanic_id) if mechanic_id else None,
            payment_mode=payment_mode,
            is_walkin=is_walkin,
        )
        db.session.add(exchange_sale)
        db.session.flush()

        for bid, qty, price in sale_rows:
            qty = int(qty)
            price = float(price)
            batch = PurchaseItem.query.get(int(bid))
            if not batch:
                continue
            product = batch.product

            db.session.add(
                SaleItem(
                    sale_id=exchange_sale.id,
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
                    date=exchange_date,
                    type="sale_out",
                    qty=-qty,
                    reference_type="sale",
                    reference_id=exchange_sale.id,
                    note=f"Sale {exchange_sale.invoice_no} (batch {batch.stock_number})",
                )
            )

        if return_rows:
            _create_return(sale, return_rows, exchange_date, note, applied_to_sale_id=exchange_sale.id)

        db.session.commit()
        sync_to_excel()
        flash("Exchange recorded — return credit applied to the new sale.", "success")
        return redirect(url_for("sales.view_sale", sale_id=exchange_sale.id))

    if not any(item.returnable_qty > 0 for item in sale.items):
        flash("Nothing left to return on this sale — use New Sale instead.", "warning")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    return _rerender()
