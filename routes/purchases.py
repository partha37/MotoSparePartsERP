from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func

from extensions import db
from excel_sync import sync_to_excel
from models import Purchase, PurchaseItem, Product, Supplier, StockMovement, Brand
from routes.server_table import ServerTable, date_filter_expr

purchases_bp = Blueprint("purchases", __name__, url_prefix="/purchases")


@purchases_bp.route("/")
@login_required
def list_purchases():
    item_agg = (
        db.session.query(
            PurchaseItem.purchase_id.label("purchase_id"),
            func.sum(PurchaseItem.qty * PurchaseItem.purchase_price).label("total"),
            func.count(PurchaseItem.id).label("item_count"),
        )
        .group_by(PurchaseItem.purchase_id)
        .subquery()
    )
    total_expr = func.coalesce(item_agg.c.total, 0.0)
    items_expr = func.coalesce(item_agg.c.item_count, 0)

    query = (
        Purchase.query
        .outerjoin(item_agg, Purchase.id == item_agg.c.purchase_id)
        .outerjoin(Supplier, Purchase.supplier_id == Supplier.id)
    )

    columns = {
        "date": ("Date", Purchase.date, date_filter_expr(Purchase.date)),
        "supplier": ("Supplier", Supplier.name),
        "invoice": ("Invoice No", Purchase.invoice_no),
        "items": ("Items", items_expr),
        "total": ("Total", total_expr),
    }
    table = ServerTable(
        query, columns,
        search_keys=["date", "supplier", "invoice", "items", "total"],
        default_sort="date", default_dir="desc",
    )
    return render_template("purchases/list.html", table=table)


def _prefill_products_from_request():
    """Builds the pre-selected line items for New Purchase when arriving from
    the Reorder report's "Add to Purchase" action (?product_ids[]=1&...) —
    each gets a `.suggested_qty` (how much to buy to get back to reorder_level)
    attached for the template to default the Qty input to, still fully editable."""
    ids = [int(i) for i in request.args.getlist("product_ids[]") if i.isdigit()]
    if not ids:
        return []
    found = {p.id: p for p in Product.query.filter(Product.id.in_(ids)).all()}
    prefill = []
    for pid in ids:
        product = found.get(pid)
        if not product:
            continue
        product.suggested_qty = max((product.reorder_level or 0) - (product.current_stock or 0), 1)
        prefill.append(product)
    return prefill


@purchases_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_purchase():
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    products = Product.query.order_by(Product.product_name.asc()).all()
    brands = Brand.query.order_by(Brand.name.asc()).all()

    if not suppliers:
        flash("Add a supplier first before recording a purchase.", "warning")
        return redirect(url_for("suppliers.new_supplier"))

    if request.method == "POST":
        supplier_id = request.form.get("supplier_id")
        purchase_date = date.fromisoformat(request.form.get("date") or date.today().isoformat())
        invoice_no = request.form.get("invoice_no", "").strip()

        product_ids = request.form.getlist("product_id[]")
        qtys = request.form.getlist("qty[]")
        prices = request.form.getlist("price_before_gst[]")
        mrps = request.form.getlist("mrp[]")
        gst_rates = request.form.getlist("gst_rate[]")
        # GST% isn't part of "is this row filled in" — it always has a usable
        # default (18%), so a blank/missing value there shouldn't block or
        # flag a row the way a missing qty/price/mrp does.
        gst_rates += [""] * (len(product_ids) - len(gst_rates))

        raw_rows = list(zip(product_ids, qtys, prices, mrps, gst_rates))
        rows = [(pid, qty, price, mrp, gst) for pid, qty, price, mrp, gst in raw_rows if pid and qty and price]
        partial_rows = [pid for pid, qty, price, mrp, gst in raw_rows if pid and not (qty and price)]

        if not supplier_id or not rows:
            flash("Select a supplier and add at least one product line.", "danger")
            return render_template(
                "purchases/form.html", suppliers=suppliers, products=products, brands=brands, today=date.today().isoformat()
            )

        if partial_rows:
            flash("Some lines have a product selected but are missing Qty or Purchase Price — fill them in or remove the line.", "danger")
            return render_template(
                "purchases/form.html", suppliers=suppliers, products=products, brands=brands, today=date.today().isoformat()
            )

        missing_mrp = []
        for pid, qty, price, mrp, gst in rows:
            if not mrp or float(mrp) <= 0:
                product = Product.query.get(int(pid))
                missing_mrp.append(product.product_name if product else f"product #{pid}")
        if missing_mrp:
            flash("Enter a valid MRP for: " + ", ".join(missing_mrp), "danger")
            return render_template(
                "purchases/form.html", suppliers=suppliers, products=products, brands=brands, today=date.today().isoformat()
            )

        purchase = Purchase(
            supplier_id=int(supplier_id), date=purchase_date, invoice_no=invoice_no
        )
        db.session.add(purchase)
        db.session.flush()  # get purchase.id

        cost_changes = []

        for pid, qty, price, mrp, gst in rows:
            qty = int(qty)
            price_before_gst = float(price)
            mrp = float(mrp)
            gst_rate = float(gst) if gst else 18.0
            purchase_price = round(price_before_gst * (1 + gst_rate / 100), 2)
            product = Product.query.get(int(pid))
            if not product:
                continue

            item = PurchaseItem(
                purchase_id=purchase.id,
                product_id=product.id,
                qty=qty,
                purchase_price=purchase_price,
                price_before_gst=price_before_gst,
                gst_rate=gst_rate,
                remaining_qty=qty,
                mrp_at_purchase=mrp,
            )
            db.session.add(item)

            product.current_stock = (product.current_stock or 0) + qty

            db.session.add(
                StockMovement(
                    product_id=product.id,
                    date=purchase_date,
                    type="purchase_in",
                    qty=qty,
                    reference_type="purchase",
                    reference_id=purchase.id,
                    note=f"Purchase from {purchase.supplier.name if purchase.supplier else ''}",
                )
            )

            old_cost = product.actual_discounted_price
            old_mrp = product.mrp
            product.update_cost_from_purchase(purchase_price, new_mrp=mrp, gst_rate=gst_rate)
            if round(old_cost or 0, 2) != product.actual_discounted_price:
                change = f"{product.part_no}: cost ₹{old_cost:.2f} → ₹{product.actual_discounted_price:.2f}"
                if round(old_mrp or 0, 2) != product.mrp:
                    change += f", MRP ₹{old_mrp:.2f} → ₹{product.mrp:.2f}"
                cost_changes.append(change)

        db.session.commit()
        sync_to_excel()
        flash("Purchase recorded and stock updated.", "success")
        if cost_changes:
            flash("Updated product cost: " + "; ".join(cost_changes), "info")
        return redirect(url_for("purchases.list_purchases"))

    return render_template(
        "purchases/form.html", suppliers=suppliers, products=products, brands=brands,
        prefill_products=_prefill_products_from_request(), today=date.today().isoformat()
    )


@purchases_bp.route("/<int:purchase_id>")
@login_required
def view_purchase(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    return render_template("purchases/view.html", purchase=purchase)
