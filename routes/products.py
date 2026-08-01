from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from extensions import db
from excel_sync import sync_to_excel
from models import Product, PurchaseItem, SaleItem

products_bp = Blueprint("products", __name__, url_prefix="/products")


def _apply_form_to_product(product, form):
    product.product_name = form.get("product_name", "").strip()
    product.part_no = form.get("part_no", "").strip()
    product.brand = form.get("brand", "").strip()
    product.category = form.get("category", "").strip()
    product.vehicle_name = form.get("vehicle_name", "").strip()
    product.unit = form.get("unit", "pc").strip() or "pc"
    product.hsn_code = form.get("hsn_code", "").strip()
    product.gst_rate = float(form.get("gst_rate") or 0)
    product.mrp = float(form.get("mrp") or 0)
    product.actual_discount_pct = float(form.get("actual_discount_pct") or 0)
    product.reorder_level = int(form.get("reorder_level") or 0)
    product.recalc_prices()


@products_bp.route("/")
@login_required
def list_products():
    q = request.args.get("q", "").strip()
    query = Product.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(Product.product_name.ilike(like), Product.part_no.ilike(like))
        )
    products = query.order_by(Product.product_name.asc()).all()
    return render_template("products/list.html", products=products, q=q)


@products_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_product():
    if request.method == "POST":
        if Product.query.filter_by(part_no=request.form.get("part_no", "").strip()).first():
            flash("A product with this Part No already exists.", "danger")
            return render_template("products/form.html", product=None, form_data=request.form)

        product = Product(current_stock=0)
        _apply_form_to_product(product, request.form)
        db.session.add(product)
        db.session.commit()
        sync_to_excel()
        flash("Product added.", "success")
        return redirect(url_for("products.list_products"))

    return render_template("products/form.html", product=None, form_data=None)


@products_bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    purchase_history = sorted(
        product.purchase_items, key=lambda item: item.purchase.date, reverse=True
    )

    if request.method == "POST":
        existing = Product.query.filter_by(part_no=request.form.get("part_no", "").strip()).first()
        if existing and existing.id != product.id:
            flash("Another product already uses this Part No.", "danger")
            return render_template(
                "products/form.html", product=product, form_data=request.form,
                purchase_history=purchase_history
            )

        _apply_form_to_product(product, request.form)
        db.session.commit()
        sync_to_excel()
        flash("Product updated.", "success")
        return redirect(url_for("products.list_products"))

    return render_template(
        "products/form.html", product=product, form_data=None, purchase_history=purchase_history
    )


@products_bp.route("/<int:product_id>/delete", methods=["POST"])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    has_purchase = PurchaseItem.query.filter_by(product_id=product.id).first()
    has_sale = SaleItem.query.filter_by(product_id=product.id).first()
    if has_purchase or has_sale:
        flash("Cannot delete: this product has purchase or sale history.", "danger")
        return redirect(url_for("products.list_products"))
    db.session.delete(product)
    db.session.commit()
    sync_to_excel()
    flash("Product deleted.", "success")
    return redirect(url_for("products.list_products"))
