from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from extensions import db
from excel_sync import sync_to_excel
from models import Supplier, Purchase, Brand

suppliers_bp = Blueprint("suppliers", __name__, url_prefix="/suppliers")


def _apply_form(supplier, form):
    supplier.name = form.get("name", "").strip()
    brand_ids = [int(bid) for bid in form.getlist("brand_id[]")]
    supplier.brands = Brand.query.filter(Brand.id.in_(brand_ids)).all() if brand_ids else []
    supplier.phone = form.get("phone", "").strip()
    supplier.address = form.get("address", "").strip()
    supplier.gstin = form.get("gstin", "").strip()


def _all_brands():
    return Brand.query.order_by(Brand.name.asc()).all()


@suppliers_bp.route("/")
@login_required
def list_suppliers():
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template("suppliers/list.html", suppliers=suppliers)


@suppliers_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_supplier():
    if request.method == "POST":
        supplier = Supplier()
        _apply_form(supplier, request.form)
        db.session.add(supplier)
        db.session.commit()
        sync_to_excel()
        flash("Supplier added.", "success")
        return redirect(url_for("suppliers.list_suppliers"))
    return render_template("suppliers/form.html", supplier=None, brands=_all_brands())


@suppliers_bp.route("/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
def edit_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    if request.method == "POST":
        _apply_form(supplier, request.form)
        db.session.commit()
        sync_to_excel()
        flash("Supplier updated.", "success")
        return redirect(url_for("suppliers.list_suppliers"))
    return render_template("suppliers/form.html", supplier=supplier, brands=_all_brands())


@suppliers_bp.route("/<int:supplier_id>/delete", methods=["POST"])
@login_required
def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    if Purchase.query.filter_by(supplier_id=supplier.id).first():
        flash("Cannot delete: this supplier has purchase records.", "danger")
        return redirect(url_for("suppliers.list_suppliers"))
    db.session.delete(supplier)
    db.session.commit()
    sync_to_excel()
    flash("Supplier deleted.", "success")
    return redirect(url_for("suppliers.list_suppliers"))
