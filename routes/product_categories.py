from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from extensions import db
from excel_sync import sync_to_excel
from models import ProductCategory, Product, CustomerCategoryDiscount, MechanicCategoryDiscount

product_categories_bp = Blueprint("product_categories", __name__, url_prefix="/product-categories")


@product_categories_bp.route("/")
@login_required
def list_categories():
    categories = ProductCategory.query.order_by(ProductCategory.name.asc()).all()
    return render_template("product_categories/list.html", categories=categories)


@product_categories_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_category():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Category name is required.", "danger")
            return render_template("product_categories/form.html", category=None)
        if ProductCategory.query.filter(db.func.lower(ProductCategory.name) == name.lower()).first():
            flash("A category with this name already exists.", "danger")
            return render_template("product_categories/form.html", category=None)
        category = ProductCategory(name=name)
        db.session.add(category)
        db.session.commit()
        sync_to_excel()
        flash("Category added.", "success")
        return redirect(url_for("product_categories.list_categories"))
    return render_template("product_categories/form.html", category=None)


@product_categories_bp.route("/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
def edit_category(category_id):
    category = ProductCategory.query.get_or_404(category_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Category name is required.", "danger")
            return render_template("product_categories/form.html", category=category)
        existing = ProductCategory.query.filter(db.func.lower(ProductCategory.name) == name.lower()).first()
        if existing and existing.id != category.id:
            flash("Another category already uses this name.", "danger")
            return render_template("product_categories/form.html", category=category)
        category.name = name
        db.session.commit()
        sync_to_excel()
        flash("Category updated.", "success")
        return redirect(url_for("product_categories.list_categories"))
    return render_template("product_categories/form.html", category=category)


@product_categories_bp.route("/<int:category_id>/delete", methods=["POST"])
@login_required
def delete_category(category_id):
    category = ProductCategory.query.get_or_404(category_id)
    in_use = (
        Product.query.filter_by(category_id=category.id).first()
        or CustomerCategoryDiscount.query.filter_by(category_id=category.id).first()
        or MechanicCategoryDiscount.query.filter_by(category_id=category.id).first()
    )
    if in_use:
        flash("Cannot delete: this category is used by a product or a discount rate.", "danger")
        return redirect(url_for("product_categories.list_categories"))
    db.session.delete(category)
    db.session.commit()
    sync_to_excel()
    flash("Category deleted.", "success")
    return redirect(url_for("product_categories.list_categories"))
