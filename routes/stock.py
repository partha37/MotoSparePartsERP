from datetime import date, timedelta

from flask import Blueprint, render_template, request
from flask_login import login_required

from models import StockMovement, Product
from routes.server_table import ServerTable, ist_date_filter_expr

stock_bp = Blueprint("stock", __name__, url_prefix="/stock")


@stock_bp.route("/")
@login_required
def ledger():
    default_from = (date.today() - timedelta(days=7)).isoformat()
    default_to = date.today().isoformat()

    date_from = request.args.get("date_from", default_from)
    date_to = request.args.get("date_to", default_to)
    product_id = request.args.get("product_id", "")

    query = StockMovement.query.join(Product, StockMovement.product_id == Product.id).filter(
        StockMovement.date >= date_from, StockMovement.date <= date_to
    )
    if product_id:
        query = query.filter(StockMovement.product_id == int(product_id))

    product_label = Product.part_no + " - " + Product.product_name
    columns = {
        "date": ("Date", StockMovement.created_at, ist_date_filter_expr(StockMovement.created_at)),
        "product": ("Product", product_label),
        "type": ("Type", StockMovement.type),
        "qty": ("Qty Change", StockMovement.qty),
        "note": ("Note", StockMovement.note),
    }
    extra_args = {"date_from": date_from, "date_to": date_to}
    if product_id:
        extra_args["product_id"] = product_id

    table = ServerTable(
        query, columns,
        search_keys=["date", "product", "type", "qty", "note"],
        default_sort="date", default_dir="desc",
        extra_args=extra_args,
    )

    products = Product.query.order_by(Product.product_name.asc()).all()

    return render_template(
        "stock/ledger.html",
        table=table,
        products=products,
        date_from=date_from,
        date_to=date_to,
        selected_product_id=product_id,
    )
