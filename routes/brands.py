from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from extensions import db
from excel_sync import sync_to_excel
from models import Brand, Product, Supplier, CustomerBrandDiscount, MechanicBrandDiscount

brands_bp = Blueprint("brands", __name__, url_prefix="/brands")


@brands_bp.route("/")
@login_required
def list_brands():
    brands = Brand.query.order_by(Brand.name.asc()).all()
    return render_template("brands/list.html", brands=brands)


@brands_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_brand():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Brand name is required.", "danger")
            return render_template("brands/form.html", brand=None)
        if Brand.query.filter(db.func.lower(Brand.name) == name.lower()).first():
            flash("A brand with this name already exists.", "danger")
            return render_template("brands/form.html", brand=None)
        brand = Brand(name=name)
        db.session.add(brand)
        db.session.commit()
        sync_to_excel()
        flash("Brand added.", "success")
        return redirect(url_for("brands.list_brands"))
    return render_template("brands/form.html", brand=None)


@brands_bp.route("/<int:brand_id>/edit", methods=["GET", "POST"])
@login_required
def edit_brand(brand_id):
    brand = Brand.query.get_or_404(brand_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Brand name is required.", "danger")
            return render_template("brands/form.html", brand=brand)
        existing = Brand.query.filter(db.func.lower(Brand.name) == name.lower()).first()
        if existing and existing.id != brand.id:
            flash("Another brand already uses this name.", "danger")
            return render_template("brands/form.html", brand=brand)
        brand.name = name
        db.session.commit()
        sync_to_excel()
        flash("Brand updated.", "success")
        return redirect(url_for("brands.list_brands"))
    return render_template("brands/form.html", brand=brand)


@brands_bp.route("/<int:brand_id>/delete", methods=["POST"])
@login_required
def delete_brand(brand_id):
    brand = Brand.query.get_or_404(brand_id)
    in_use = (
        Product.query.filter_by(brand_id=brand.id).first()
        or Supplier.query.filter_by(brand_id=brand.id).first()
        or CustomerBrandDiscount.query.filter_by(brand_id=brand.id).first()
        or MechanicBrandDiscount.query.filter_by(brand_id=brand.id).first()
    )
    if in_use:
        flash("Cannot delete: this brand is used by a product, supplier, or a discount rate.", "danger")
        return redirect(url_for("brands.list_brands"))
    db.session.delete(brand)
    db.session.commit()
    sync_to_excel()
    flash("Brand deleted.", "success")
    return redirect(url_for("brands.list_brands"))
