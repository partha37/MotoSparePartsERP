from datetime import date

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func

from extensions import db
from models import Product, Sale, SaleItem

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/")


@dashboard_bp.route("/")
@login_required
def index():
    today = date.today()

    todays_sales = Sale.query.filter_by(date=today).all()
    todays_total = sum(s.total for s in todays_sales)
    todays_count = len(todays_sales)

    low_stock_products = (
        Product.query.filter(Product.current_stock <= Product.reorder_level)
        .order_by(Product.current_stock.asc())
        .all()
    )

    total_products = Product.query.count()
    total_stock_value = db.session.query(
        func.sum(Product.current_stock * Product.actual_discounted_price)
    ).scalar() or 0

    return render_template(
        "dashboard/index.html",
        todays_total=todays_total,
        todays_count=todays_count,
        low_stock_products=low_stock_products,
        total_products=total_products,
        total_stock_value=round(total_stock_value, 2),
    )
