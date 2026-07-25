from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from extensions import db
from models import Sale, SaleItem, Product, Customer, Mechanic, StockMovement, ShopSettings

sales_bp = Blueprint("sales", __name__, url_prefix="/sales")


def _next_invoice_no():
    last = Sale.query.order_by(Sale.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"INV-{next_id:05d}"


@sales_bp.route("/")
@login_required
def list_sales():
    sales = Sale.query.order_by(Sale.date.desc(), Sale.id.desc()).all()
    return render_template("sales/list.html", sales=sales)


@sales_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_sale():
    products = Product.query.order_by(Product.product_name.asc()).all()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    mechanics = Mechanic.query.order_by(Mechanic.name.asc()).all()

    if request.method == "POST":
        sale_date = date.fromisoformat(request.form.get("date") or date.today().isoformat())
        customer_id = request.form.get("customer_id") or None
        mechanic_id = request.form.get("mechanic_id") or None
        payment_mode = request.form.get("payment_mode", "cash")
        amount_paid = float(request.form.get("amount_paid") or 0)

        product_ids = request.form.getlist("product_id[]")
        qtys = request.form.getlist("qty[]")
        prices = request.form.getlist("selling_price[]")

        rows = [
            (pid, qty, price)
            for pid, qty, price in zip(product_ids, qtys, prices)
            if pid and qty and price
        ]

        if not rows:
            flash("Add at least one product to the sale.", "danger")
            return render_template(
                "sales/form.html", products=products, customers=customers,
                mechanics=mechanics, today=date.today().isoformat()
            )

        # Validate stock availability before committing anything.
        shortages = []
        for pid, qty, _price in rows:
            product = Product.query.get(int(pid))
            qty = int(qty)
            if product and qty > product.current_stock:
                shortages.append(f"{product.product_name} (have {product.current_stock}, need {qty})")

        if shortages:
            flash("Not enough stock for: " + ", ".join(shortages), "danger")
            return render_template(
                "sales/form.html", products=products, customers=customers,
                mechanics=mechanics, today=date.today().isoformat()
            )

        sale = Sale(
            invoice_no=_next_invoice_no(),
            date=sale_date,
            customer_id=int(customer_id) if customer_id else None,
            mechanic_id=int(mechanic_id) if mechanic_id else None,
            payment_mode=payment_mode,
            amount_paid=amount_paid,
        )
        db.session.add(sale)
        db.session.flush()

        for pid, qty, price in rows:
            qty = int(qty)
            price = float(price)
            product = Product.query.get(int(pid))
            if not product:
                continue

            db.session.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    qty=qty,
                    selling_price=price,
                    gst_rate=product.gst_rate,
                )
            )

            product.current_stock = (product.current_stock or 0) - qty

            db.session.add(
                StockMovement(
                    product_id=product.id,
                    date=sale_date,
                    type="sale_out",
                    qty=-qty,
                    reference_type="sale",
                    reference_id=sale.id,
                    note=f"Sale {sale.invoice_no}",
                )
            )

        db.session.commit()
        flash("Sale recorded and stock updated.", "success")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    return render_template(
        "sales/form.html", products=products, customers=customers,
        mechanics=mechanics, today=date.today().isoformat()
    )


@sales_bp.route("/<int:sale_id>")
@login_required
def view_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    shop = ShopSettings.query.first() or ShopSettings()
    return render_template("sales/view.html", sale=sale, shop=shop)
