from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, render_template, request
from flask_login import login_required

from models import Sale, SaleItem, Purchase, Product

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _date_range_args():
    default_from = (date.today() - timedelta(days=30)).isoformat()
    default_to = date.today().isoformat()
    date_from = request.args.get("date_from", default_from)
    date_to = request.args.get("date_to", default_to)
    return date_from, date_to


@reports_bp.route("/")
@login_required
def index():
    return render_template("reports/index.html")


@reports_bp.route("/daily-sales")
@login_required
def daily_sales():
    date_from, date_to = _date_range_args()
    sales = Sale.query.filter(Sale.date >= date_from, Sale.date <= date_to).all()

    by_date = defaultdict(lambda: {"count": 0, "total": 0.0})
    for s in sales:
        by_date[str(s.date)]["count"] += 1
        by_date[str(s.date)]["total"] += s.total

    rows = sorted(by_date.items(), key=lambda kv: kv[0], reverse=True)
    grand_total = sum(v["total"] for _, v in rows)

    return render_template(
        "reports/daily_sales.html", rows=rows, grand_total=grand_total,
        date_from=date_from, date_to=date_to
    )


@reports_bp.route("/mechanic-wise")
@login_required
def mechanic_wise():
    date_from, date_to = _date_range_args()
    sales = Sale.query.filter(Sale.date >= date_from, Sale.date <= date_to).all()

    by_mechanic = defaultdict(lambda: {"count": 0, "total": 0.0})
    for s in sales:
        key = s.mechanic.name if s.mechanic else "No mechanic"
        by_mechanic[key]["count"] += 1
        by_mechanic[key]["total"] += s.total

    rows = sorted(by_mechanic.items(), key=lambda kv: kv[1]["total"], reverse=True)

    return render_template(
        "reports/mechanic_wise.html", rows=rows, date_from=date_from, date_to=date_to
    )


@reports_bp.route("/customer-wise")
@login_required
def customer_wise():
    date_from, date_to = _date_range_args()
    sales = Sale.query.filter(Sale.date >= date_from, Sale.date <= date_to).all()

    by_customer = defaultdict(lambda: {"count": 0, "total": 0.0})
    for s in sales:
        key = s.customer.name if s.customer else "Walk-in"
        by_customer[key]["count"] += 1
        by_customer[key]["total"] += s.total

    rows = sorted(by_customer.items(), key=lambda kv: kv[1]["total"], reverse=True)

    return render_template(
        "reports/customer_wise.html", rows=rows, date_from=date_from, date_to=date_to
    )


@reports_bp.route("/best-sellers")
@login_required
def best_sellers():
    date_from, date_to = _date_range_args()
    items = (
        SaleItem.query.join(Sale)
        .filter(Sale.date >= date_from, Sale.date <= date_to)
        .all()
    )

    by_product = defaultdict(lambda: {"qty": 0, "revenue": 0.0})
    for item in items:
        key = f"{item.product.part_no} - {item.product.product_name}"
        by_product[key]["qty"] += item.qty
        by_product[key]["revenue"] += item.line_total

    rows = sorted(by_product.items(), key=lambda kv: kv[1]["qty"], reverse=True)

    return render_template(
        "reports/best_sellers.html", rows=rows, date_from=date_from, date_to=date_to
    )


@reports_bp.route("/profit-margin")
@login_required
def profit_margin():
    date_from, date_to = _date_range_args()
    items = (
        SaleItem.query.join(Sale)
        .filter(Sale.date >= date_from, Sale.date <= date_to)
        .all()
    )

    by_product = defaultdict(lambda: {"qty": 0, "revenue": 0.0, "cost": 0.0})
    for item in items:
        key = f"{item.product.part_no} - {item.product.product_name}"
        # Use the actual batch's purchase price when known (accurate historical cost);
        # fall back to the product's current cost for sales made before batch tracking existed.
        unit_cost = (
            item.purchase_item.purchase_price if item.purchase_item
            else (item.product.actual_discounted_price or 0)
        )
        by_product[key]["qty"] += item.qty
        by_product[key]["revenue"] += item.line_total
        by_product[key]["cost"] += item.qty * unit_cost

    rows = []
    total_profit = 0.0
    for name, v in by_product.items():
        profit = round(v["revenue"] - v["cost"], 2)
        total_profit += profit
        rows.append((name, v["qty"], round(v["revenue"], 2), round(v["cost"], 2), profit))
    rows.sort(key=lambda r: r[4], reverse=True)

    return render_template(
        "reports/profit_margin.html", rows=rows, total_profit=round(total_profit, 2),
        date_from=date_from, date_to=date_to
    )


@reports_bp.route("/supplier-summary")
@login_required
def supplier_summary():
    date_from, date_to = _date_range_args()
    purchases = Purchase.query.filter(Purchase.date >= date_from, Purchase.date <= date_to).all()

    by_supplier = defaultdict(lambda: {"count": 0, "total": 0.0})
    for p in purchases:
        key = p.supplier.name if p.supplier else "Unknown"
        by_supplier[key]["count"] += 1
        by_supplier[key]["total"] += p.total

    rows = sorted(by_supplier.items(), key=lambda kv: kv[1]["total"], reverse=True)

    return render_template(
        "reports/supplier_summary.html", rows=rows, date_from=date_from, date_to=date_to
    )


@reports_bp.route("/low-stock")
@login_required
def low_stock():
    products = (
        Product.query.filter(Product.current_stock <= Product.reorder_level)
        .order_by(Product.current_stock.asc())
        .all()
    )
    return render_template("reports/low_stock.html", products=products)
