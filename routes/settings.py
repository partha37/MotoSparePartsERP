import csv
import io
import os
from datetime import date

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, Response, send_file, current_app
)
from flask_login import login_required

from extensions import db
from models import ShopSettings, Product, Customer, Mechanic, Supplier, Sale, Purchase

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

EXPORTABLE = {
    "products": (Product, ["id", "part_no", "product_name", "brand", "category", "mrp",
                            "actual_discount_pct", "actual_discounted_price",
                            "selling_discount_pct", "mrp_discounted_price",
                            "current_stock", "reorder_level"]),
    "customers": (Customer, ["id", "name", "phone", "address", "vehicle_model"]),
    "mechanics": (Mechanic, ["id", "name", "phone", "garage_name", "commission_pct"]),
    "suppliers": (Supplier, ["id", "name", "brand", "phone", "address", "gstin"]),
    "sales": (Sale, ["id", "invoice_no", "date", "customer_id", "mechanic_id",
                      "payment_mode", "amount_paid"]),
    "purchases": (Purchase, ["id", "supplier_id", "date", "invoice_no"]),
}


@settings_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    shop = ShopSettings.query.first()
    if not shop:
        shop = ShopSettings()
        db.session.add(shop)
        db.session.commit()

    if request.method == "POST":
        shop.shop_name = request.form.get("shop_name", "").strip()
        shop.address = request.form.get("address", "").strip()
        shop.phone = request.form.get("phone", "").strip()
        shop.gstin = request.form.get("gstin", "").strip()
        db.session.commit()
        flash("Shop settings saved.", "success")
        return redirect(url_for("settings.index"))

    return render_template("settings/index.html", shop=shop, exportable=EXPORTABLE.keys())


@settings_bp.route("/export/<table_name>")
@login_required
def export_csv(table_name):
    if table_name not in EXPORTABLE:
        flash("Unknown export table.", "danger")
        return redirect(url_for("settings.index"))

    model, columns = EXPORTABLE[table_name]
    rows = model.query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([getattr(row, col) for col in columns])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={table_name}.csv"},
    )


@settings_bp.route("/backup")
@login_required
def backup():
    db_path = os.path.join(current_app.root_path, "instance", "erp.db")
    filename = f"erp-backup-{date.today().isoformat()}.db"
    return send_file(db_path, as_attachment=True, download_name=filename)
