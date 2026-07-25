from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from extensions import db
from models import Purchase, PurchaseItem, Product, Supplier, StockMovement

purchases_bp = Blueprint("purchases", __name__, url_prefix="/purchases")


@purchases_bp.route("/")
@login_required
def list_purchases():
    purchases = Purchase.query.order_by(Purchase.date.desc(), Purchase.id.desc()).all()
    return render_template("purchases/list.html", purchases=purchases)


@purchases_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_purchase():
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    products = Product.query.order_by(Product.product_name.asc()).all()

    if not suppliers:
        flash("Add a supplier first before recording a purchase.", "warning")
        return redirect(url_for("suppliers.new_supplier"))

    if request.method == "POST":
        supplier_id = request.form.get("supplier_id")
        purchase_date = date.fromisoformat(request.form.get("date") or date.today().isoformat())
        invoice_no = request.form.get("invoice_no", "").strip()

        product_ids = request.form.getlist("product_id[]")
        qtys = request.form.getlist("qty[]")
        prices = request.form.getlist("purchase_price[]")

        rows = [
            (pid, qty, price)
            for pid, qty, price in zip(product_ids, qtys, prices)
            if pid and qty and price
        ]

        if not supplier_id or not rows:
            flash("Select a supplier and add at least one product line.", "danger")
            return render_template(
                "purchases/form.html", suppliers=suppliers, products=products, today=date.today().isoformat()
            )

        purchase = Purchase(
            supplier_id=int(supplier_id), date=purchase_date, invoice_no=invoice_no
        )
        db.session.add(purchase)
        db.session.flush()  # get purchase.id

        for pid, qty, price in rows:
            qty = int(qty)
            price = float(price)
            product = Product.query.get(int(pid))
            if not product:
                continue

            item = PurchaseItem(
                purchase_id=purchase.id, product_id=product.id, qty=qty, purchase_price=price
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

        db.session.commit()
        flash("Purchase recorded and stock updated.", "success")
        return redirect(url_for("purchases.list_purchases"))

    return render_template(
        "purchases/form.html", suppliers=suppliers, products=products, today=date.today().isoformat()
    )


@purchases_bp.route("/<int:purchase_id>")
@login_required
def view_purchase(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    return render_template("purchases/view.html", purchase=purchase)
