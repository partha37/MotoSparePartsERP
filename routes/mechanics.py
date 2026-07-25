from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from extensions import db
from models import Mechanic, Sale

mechanics_bp = Blueprint("mechanics", __name__, url_prefix="/mechanics")


def _apply_form(mechanic, form):
    mechanic.name = form.get("name", "").strip()
    mechanic.phone = form.get("phone", "").strip()
    mechanic.garage_name = form.get("garage_name", "").strip()
    mechanic.commission_pct = float(form.get("commission_pct") or 0)


@mechanics_bp.route("/")
@login_required
def list_mechanics():
    mechanics = Mechanic.query.order_by(Mechanic.name.asc()).all()
    return render_template("mechanics/list.html", mechanics=mechanics)


@mechanics_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_mechanic():
    if request.method == "POST":
        mechanic = Mechanic()
        _apply_form(mechanic, request.form)
        db.session.add(mechanic)
        db.session.commit()
        flash("Mechanic added.", "success")
        return redirect(url_for("mechanics.list_mechanics"))
    return render_template("mechanics/form.html", mechanic=None)


@mechanics_bp.route("/<int:mechanic_id>/edit", methods=["GET", "POST"])
@login_required
def edit_mechanic(mechanic_id):
    mechanic = Mechanic.query.get_or_404(mechanic_id)
    if request.method == "POST":
        _apply_form(mechanic, request.form)
        db.session.commit()
        flash("Mechanic updated.", "success")
        return redirect(url_for("mechanics.list_mechanics"))
    return render_template("mechanics/form.html", mechanic=mechanic)


@mechanics_bp.route("/<int:mechanic_id>")
@login_required
def view_mechanic(mechanic_id):
    mechanic = Mechanic.query.get_or_404(mechanic_id)
    sales = Sale.query.filter_by(mechanic_id=mechanic.id).order_by(Sale.date.desc()).all()
    return render_template("mechanics/view.html", mechanic=mechanic, sales=sales)


@mechanics_bp.route("/<int:mechanic_id>/delete", methods=["POST"])
@login_required
def delete_mechanic(mechanic_id):
    mechanic = Mechanic.query.get_or_404(mechanic_id)
    if Sale.query.filter_by(mechanic_id=mechanic.id).first():
        flash("Cannot delete: this mechanic has sale records.", "danger")
        return redirect(url_for("mechanics.list_mechanics"))
    db.session.delete(mechanic)
    db.session.commit()
    flash("Mechanic deleted.", "success")
    return redirect(url_for("mechanics.list_mechanics"))
