from datetime import date, timedelta

from flask import Blueprint, render_template, request
from flask_login import login_required

from models import StockMovement, Product

stock_bp = Blueprint("stock", __name__, url_prefix="/stock")


@stock_bp.route("/")
@login_required
def ledger():
    default_from = (date.today() - timedelta(days=7)).isoformat()
    default_to = date.today().isoformat()

    date_from = request.args.get("date_from", default_from)
    date_to = request.args.get("date_to", default_to)
    product_id = request.args.get("product_id", "")

    query = StockMovement.query.filter(
        StockMovement.date >= date_from, StockMovement.date <= date_to
    )
    if product_id:
        query = query.filter(StockMovement.product_id == int(product_id))

    movements = query.order_by(StockMovement.date.desc(), StockMovement.id.desc()).all()
    products = Product.query.order_by(Product.product_name.asc()).all()

    return render_template(
        "stock/ledger.html",
        movements=movements,
        products=products,
        date_from=date_from,
        date_to=date_to,
        selected_product_id=product_id,
    )
