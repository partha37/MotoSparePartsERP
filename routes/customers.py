from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from extensions import db
from excel_sync import sync_to_excel
from models import Customer, Sale

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


def _apply_form(customer, form):
    customer.name = form.get("name", "").strip()
    customer.phone = form.get("phone", "").strip()
    customer.address = form.get("address", "").strip()
    customer.vehicle_model = form.get("vehicle_model", "").strip()
    customer.discount_pct = float(form.get("discount_pct") or 0)


@customers_bp.route("/")
@login_required
def list_customers():
    customers = Customer.query.order_by(Customer.name.asc()).all()
    return render_template("customers/list.html", customers=customers)


@customers_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_customer():
    if request.method == "POST":
        customer = Customer()
        _apply_form(customer, request.form)
        db.session.add(customer)
        db.session.commit()
        sync_to_excel()
        flash("Customer added.", "success")
        return redirect(url_for("customers.list_customers"))
    return render_template("customers/form.html", customer=None)


@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if request.method == "POST":
        _apply_form(customer, request.form)
        db.session.commit()
        sync_to_excel()
        flash("Customer updated.", "success")
        return redirect(url_for("customers.list_customers"))
    return render_template("customers/form.html", customer=customer)


@customers_bp.route("/<int:customer_id>")
@login_required
def view_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    sales = Sale.query.filter_by(customer_id=customer.id).order_by(Sale.date.desc()).all()
    return render_template("customers/view.html", customer=customer, sales=sales)


@customers_bp.route("/<int:customer_id>/delete", methods=["POST"])
@login_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if Sale.query.filter_by(customer_id=customer.id).first():
        flash("Cannot delete: this customer has sale records.", "danger")
        return redirect(url_for("customers.list_customers"))
    db.session.delete(customer)
    db.session.commit()
    sync_to_excel()
    flash("Customer deleted.", "success")
    return redirect(url_for("customers.list_customers"))
