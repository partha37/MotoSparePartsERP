import csv
import io
import os
from datetime import date

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, Response, send_file, current_app
)
from flask_login import login_required

from extensions import db
from excel_sync import sync_to_excel, excel_path, cloud_backup_status
from models import (
    ShopSettings, Product, Customer, CustomerBrandDiscount, Mechanic, MechanicBrandDiscount,
    Supplier, Sale, Purchase, Payment, Brand, SaleReturn,
)

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

EXPORTABLE = {
    "products": (Product, ["id", "part_no", "product_name", "brand_name", "category", "vehicle_name",
                            "unit", "mrp", "actual_discount_pct", "actual_discounted_price",
                            "current_stock", "reorder_level"]),
    "customers": (Customer, ["id", "name", "phone", "address", "vehicle_model"]),
    "mechanics": (Mechanic, ["id", "name", "phone", "garage_name"]),
    "suppliers": (Supplier, ["id", "name", "brand_name", "phone", "address", "gstin"]),
    "sales": (Sale, ["id", "invoice_no", "date", "customer_id", "mechanic_id",
                      "payment_mode", "amount_paid"]),
    "purchases": (Purchase, ["id", "supplier_id", "date", "invoice_no"]),
    "payments": (Payment, ["id", "sale_id", "invoice_no", "date", "amount", "payment_mode", "note"]),
    "sale_returns": (SaleReturn, ["id", "sale_id", "invoice_no", "applied_to_sale_id", "return_no", "date", "note", "refund_amount"]),
    "brands": (Brand, ["id", "name"]),
    "customer_brand_discounts": (CustomerBrandDiscount, ["id", "customer_id", "customer_name", "brand_name", "discount_pct"]),
    "mechanic_brand_discounts": (MechanicBrandDiscount, ["id", "mechanic_id", "mechanic_name", "brand_name", "discount_pct"]),
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
        sync_to_excel()
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


@settings_bp.route("/export/excel")
@login_required
def export_excel():
    sync_to_excel()
    path = excel_path()
    if not os.path.exists(path):
        flash("Excel mirror hasn't been created yet — make any change first.", "warning")
        return redirect(url_for("settings.index"))
    return send_file(path, as_attachment=True, download_name="erp_data.xlsx")


@settings_bp.route("/backup")
@login_required
def backup():
    db_path = os.path.join(current_app.root_path, "instance", "erp.db")
    filename = f"erp-backup-{date.today().isoformat()}.db"
    return send_file(db_path, as_attachment=True, download_name=filename)


@settings_bp.route("/cloud-backup")
@login_required
def cloud_backup():
    return render_template("settings/cloud_backup.html", status=cloud_backup_status())


@settings_bp.route("/cloud-backup/sync-now", methods=["POST"])
@login_required
def cloud_backup_sync_now():
    """Manual "sync now" button — just re-runs the same sync_to_excel() every
    mutating route already calls, so it isn't a separate code path from the
    automatic sync. Flashes based on the status *after* syncing, since
    sync_to_excel() itself never raises (best-effort by design)."""
    sync_to_excel()
    status = cloud_backup_status()
    if status["connected"]:
        flash("Synced to the cloud backup folder.", "success")
    elif status["configured"]:
        flash("Cloud backup folder isn't reachable right now — check Google Drive is running and signed in.", "warning")
    else:
        flash("Cloud backup isn't configured (CLOUD_BACKUP_DIR isn't set).", "warning")
    return redirect(url_for("settings.cloud_backup"))
