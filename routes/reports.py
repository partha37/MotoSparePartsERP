from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, render_template, request
from flask_login import login_required

from models import Sale, SaleItem, Purchase, Product, Customer, Mechanic, Supplier, Brand

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


@reports_bp.route("/outstanding-dues")
@login_required
def outstanding_dues():
    all_sales = Sale.query.order_by(Sale.date.asc(), Sale.id.asc()).all()
    rows = [s for s in all_sales if s.balance_due > 0]
    grand_total = round(sum(s.balance_due for s in rows), 2)
    return render_template("reports/outstanding_dues.html", rows=rows, grand_total=grand_total)


@reports_bp.route("/daily-sales")
@login_required
def daily_sales():
    date_from, date_to = _date_range_args()
    group_by = request.args.get("group", "day")
    if group_by not in ("day", "week"):
        group_by = "day"

    sales = (
        Sale.query.filter(Sale.date >= date_from, Sale.date <= date_to)
        .order_by(Sale.date.asc(), Sale.id.asc())
        .all()
    )

    by_period = defaultdict(lambda: {"count": 0, "total": 0.0})
    by_product = defaultdict(lambda: {"qty": 0, "revenue": 0.0, "cost": 0.0, "discount_amount": 0.0, "mrp_total": 0.0})
    total_revenue = 0.0
    total_cost = 0.0
    total_discount = 0.0
    total_mrp = 0.0

    for s in sales:
        period = _period_label(s.date, group_by)
        by_period[period]["count"] += 1
        by_period[period]["total"] += s.total

        for item in s.items:
            mrp = item.mrp_at_sale or 0
            unit_cost = (
                item.purchase_item.purchase_price if item.purchase_item
                else (item.product.actual_discounted_price or 0)
            )
            line_revenue = item.line_total
            line_cost = round(item.qty * unit_cost, 2)
            line_discount = round((mrp - item.selling_price) * item.qty, 2) if mrp else 0
            product_key = f"{item.product.part_no} - {item.product.product_name}"

            by_product[product_key]["qty"] += item.qty
            by_product[product_key]["revenue"] += line_revenue
            by_product[product_key]["cost"] += line_cost
            by_product[product_key]["discount_amount"] += line_discount
            by_product[product_key]["mrp_total"] += mrp * item.qty

            total_revenue += line_revenue
            total_cost += line_cost
            total_discount += line_discount
            total_mrp += mrp * item.qty

    time_series = sorted(by_period.items(), key=lambda kv: kv[0])

    product_rows = []
    for name, v in by_product.items():
        profit = round(v["revenue"] - v["cost"], 2)
        profit_pct = round(profit / v["revenue"] * 100, 2) if v["revenue"] else 0
        avg_discount_pct = round(v["discount_amount"] / v["mrp_total"] * 100, 2) if v["mrp_total"] else 0
        product_rows.append({
            "name": name, "qty": v["qty"], "revenue": round(v["revenue"], 2),
            "discount_amount": round(v["discount_amount"], 2), "avg_discount_pct": avg_discount_pct,
            "cost": round(v["cost"], 2), "profit": profit, "profit_pct": profit_pct,
        })
    product_rows.sort(key=lambda r: r["revenue"], reverse=True)

    total_profit = round(total_revenue - total_cost, 2)
    summary = {
        "invoices": len(sales),
        "total_revenue": round(total_revenue, 2),
        "total_discount": round(total_discount, 2),
        "avg_discount_pct": round(total_discount / total_mrp * 100, 2) if total_mrp else 0,
        "total_cost": round(total_cost, 2),
        "total_profit": total_profit,
        "profit_pct": round(total_profit / total_revenue * 100, 2) if total_revenue else 0,
    }

    return render_template(
        "reports/daily_sales.html", summary=summary,
        time_series=time_series, product_rows=product_rows,
        date_from=date_from, date_to=date_to, group_by=group_by,
    )


@reports_bp.route("/mechanic-wise")
@login_required
def mechanic_wise():
    date_from, date_to = _date_range_args()
    sales = Sale.query.filter(Sale.date >= date_from, Sale.date <= date_to).all()

    by_mechanic = defaultdict(lambda: {"id": None, "name": "No mechanic", "count": 0, "total": 0.0})
    for s in sales:
        key = s.mechanic_id or 0
        by_mechanic[key]["id"] = s.mechanic_id
        by_mechanic[key]["name"] = s.mechanic.name if s.mechanic else "No mechanic"
        by_mechanic[key]["count"] += 1
        by_mechanic[key]["total"] += s.total

    rows = sorted(by_mechanic.values(), key=lambda v: v["total"], reverse=True)

    return render_template(
        "reports/mechanic_wise.html", rows=rows, date_from=date_from, date_to=date_to
    )


@reports_bp.route("/customer-wise")
@login_required
def customer_wise():
    date_from, date_to = _date_range_args()
    sales = Sale.query.filter(Sale.date >= date_from, Sale.date <= date_to).all()

    by_customer = defaultdict(lambda: {"id": None, "name": "Walk-in", "count": 0, "total": 0.0})
    for s in sales:
        key = s.customer_id or 0
        by_customer[key]["id"] = s.customer_id
        by_customer[key]["name"] = s.customer.name if s.customer else "Walk-in"
        by_customer[key]["count"] += 1
        by_customer[key]["total"] += s.total

    rows = sorted(by_customer.values(), key=lambda v: v["total"], reverse=True)

    return render_template(
        "reports/customer_wise.html", rows=rows, date_from=date_from, date_to=date_to
    )


def _period_label(d, group_by):
    """Buckets a date into either its ISO date string (day) or ISO
    year-week string (week), used to group a contact's sales for the
    "purchases over time" chart/table."""
    if group_by == "week":
        iso_year, iso_week, _ = d.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return d.isoformat()


def _contact_detail(kind, contact_id):
    if kind == "customer":
        contact = Customer.query.get_or_404(contact_id)
        sales_q = Sale.query.filter(Sale.customer_id == contact_id)
    else:
        contact = Mechanic.query.get_or_404(contact_id)
        sales_q = Sale.query.filter(Sale.mechanic_id == contact_id)

    date_from, date_to = _date_range_args()
    group_by = request.args.get("group", "day")
    if group_by not in ("day", "week"):
        group_by = "day"

    sales = (
        sales_q.filter(Sale.date >= date_from, Sale.date <= date_to)
        .order_by(Sale.date.asc(), Sale.id.asc())
        .all()
    )

    by_period = defaultdict(lambda: {"count": 0, "total": 0.0})
    by_product = defaultdict(lambda: {"qty": 0, "revenue": 0.0, "cost": 0.0, "discount_amount": 0.0, "mrp_total": 0.0})
    item_rows = []
    total_revenue = 0.0
    total_cost = 0.0
    total_discount = 0.0
    total_mrp = 0.0

    for s in sales:
        period = _period_label(s.date, group_by)
        by_period[period]["count"] += 1
        by_period[period]["total"] += s.total

        for item in s.items:
            mrp = item.mrp_at_sale or 0
            unit_cost = (
                item.purchase_item.purchase_price if item.purchase_item
                else (item.product.actual_discounted_price or 0)
            )
            line_revenue = item.line_total
            line_cost = round(item.qty * unit_cost, 2)
            line_discount = round((mrp - item.selling_price) * item.qty, 2) if mrp else 0
            product_key = f"{item.product.part_no} - {item.product.product_name}"

            item_rows.append({
                "date": s.date, "sale_id": s.id, "invoice_no": s.invoice_no,
                "product_name": product_key, "qty": item.qty, "mrp": mrp,
                "discount_pct": item.discount_pct, "price": item.selling_price,
                "line_total": line_revenue,
            })

            by_product[product_key]["qty"] += item.qty
            by_product[product_key]["revenue"] += line_revenue
            by_product[product_key]["cost"] += line_cost
            by_product[product_key]["discount_amount"] += line_discount
            by_product[product_key]["mrp_total"] += mrp * item.qty

            total_revenue += line_revenue
            total_cost += line_cost
            total_discount += line_discount
            total_mrp += mrp * item.qty

    time_series = sorted(by_period.items(), key=lambda kv: kv[0])
    item_rows.sort(key=lambda r: (r["date"], r["sale_id"]), reverse=True)

    product_rows = []
    for name, v in by_product.items():
        profit = round(v["revenue"] - v["cost"], 2)
        profit_pct = round(profit / v["revenue"] * 100, 2) if v["revenue"] else 0
        avg_discount_pct = round(v["discount_amount"] / v["mrp_total"] * 100, 2) if v["mrp_total"] else 0
        product_rows.append({
            "name": name, "qty": v["qty"], "revenue": round(v["revenue"], 2),
            "discount_amount": round(v["discount_amount"], 2), "avg_discount_pct": avg_discount_pct,
            "cost": round(v["cost"], 2), "profit": profit, "profit_pct": profit_pct,
        })
    product_rows.sort(key=lambda r: r["revenue"], reverse=True)

    total_profit = round(total_revenue - total_cost, 2)
    summary = {
        "invoices": len(sales),
        "total_revenue": round(total_revenue, 2),
        "total_discount": round(total_discount, 2),
        "avg_discount_pct": round(total_discount / total_mrp * 100, 2) if total_mrp else 0,
        "total_cost": round(total_cost, 2),
        "total_profit": total_profit,
        "profit_pct": round(total_profit / total_revenue * 100, 2) if total_revenue else 0,
    }

    return render_template(
        "reports/contact_detail.html",
        kind=kind, contact=contact, summary=summary,
        time_series=time_series, product_rows=product_rows, item_rows=item_rows,
        date_from=date_from, date_to=date_to, group_by=group_by,
    )


@reports_bp.route("/customer/<int:contact_id>")
@login_required
def customer_detail(contact_id):
    return _contact_detail("customer", contact_id)


@reports_bp.route("/mechanic/<int:contact_id>")
@login_required
def mechanic_detail(contact_id):
    return _contact_detail("mechanic", contact_id)


@reports_bp.route("/best-sellers")
@login_required
def best_sellers():
    date_from, date_to = _date_range_args()
    items = (
        SaleItem.query.join(Sale)
        .filter(Sale.date >= date_from, Sale.date <= date_to)
        .all()
    )

    by_product = defaultdict(lambda: {"id": None, "name": "", "qty": 0, "revenue": 0.0})
    for item in items:
        key = item.product_id
        by_product[key]["id"] = item.product_id
        by_product[key]["name"] = f"{item.product.part_no} - {item.product.product_name}"
        by_product[key]["qty"] += item.qty
        by_product[key]["revenue"] += item.line_total

    rows = sorted(by_product.values(), key=lambda v: v["qty"], reverse=True)

    return render_template(
        "reports/best_sellers.html", rows=rows, date_from=date_from, date_to=date_to
    )


def _product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    date_from, date_to = _date_range_args()
    group_by = request.args.get("group", "day")
    if group_by not in ("day", "week"):
        group_by = "day"

    items = (
        SaleItem.query.join(Sale)
        .filter(SaleItem.product_id == product_id, Sale.date >= date_from, Sale.date <= date_to)
        .order_by(Sale.date.asc(), Sale.id.asc())
        .all()
    )

    by_period = defaultdict(lambda: {"count": 0, "qty": 0, "revenue": 0.0})
    by_contact = defaultdict(lambda: {"name": "", "qty": 0, "revenue": 0.0, "discount_amount": 0.0, "mrp_total": 0.0})
    item_rows = []
    total_revenue = 0.0
    total_cost = 0.0
    total_discount = 0.0
    total_mrp = 0.0
    total_qty = 0

    for item in items:
        s = item.sale
        period = _period_label(s.date, group_by)
        by_period[period]["count"] += 1
        by_period[period]["qty"] += item.qty
        by_period[period]["revenue"] += item.line_total

        mrp = item.mrp_at_sale or 0
        unit_cost = (
            item.purchase_item.purchase_price if item.purchase_item
            else (item.product.actual_discounted_price or 0)
        )
        line_revenue = item.line_total
        line_cost = round(item.qty * unit_cost, 2)
        line_discount = round((mrp - item.selling_price) * item.qty, 2) if mrp else 0

        if s.mechanic_id:
            contact_key = ("mechanic", s.mechanic_id)
            contact_name = s.mechanic.name
        elif s.customer_id:
            contact_key = ("customer", s.customer_id)
            contact_name = s.customer.name
        else:
            contact_key = ("walkin", 0)
            contact_name = "Walk-in"

        item_rows.append({
            "date": s.date, "sale_id": s.id, "invoice_no": s.invoice_no,
            "contact_name": contact_name, "qty": item.qty, "mrp": mrp,
            "discount_pct": item.discount_pct, "price": item.selling_price,
            "line_total": line_revenue,
        })

        by_contact[contact_key]["name"] = contact_name
        by_contact[contact_key]["qty"] += item.qty
        by_contact[contact_key]["revenue"] += line_revenue
        by_contact[contact_key]["discount_amount"] += line_discount
        by_contact[contact_key]["mrp_total"] += mrp * item.qty

        total_revenue += line_revenue
        total_cost += line_cost
        total_discount += line_discount
        total_mrp += mrp * item.qty
        total_qty += item.qty

    time_series = sorted(by_period.items(), key=lambda kv: kv[0])
    item_rows.sort(key=lambda r: (r["date"], r["sale_id"]), reverse=True)

    contact_rows = []
    for v in by_contact.values():
        avg_discount_pct = round(v["discount_amount"] / v["mrp_total"] * 100, 2) if v["mrp_total"] else 0
        contact_rows.append({
            "name": v["name"], "qty": v["qty"], "revenue": round(v["revenue"], 2),
            "discount_amount": round(v["discount_amount"], 2), "avg_discount_pct": avg_discount_pct,
        })
    contact_rows.sort(key=lambda r: r["revenue"], reverse=True)

    total_profit = round(total_revenue - total_cost, 2)
    summary = {
        "qty_sold": total_qty,
        "total_revenue": round(total_revenue, 2),
        "total_discount": round(total_discount, 2),
        "avg_discount_pct": round(total_discount / total_mrp * 100, 2) if total_mrp else 0,
        "total_cost": round(total_cost, 2),
        "total_profit": total_profit,
        "profit_pct": round(total_profit / total_revenue * 100, 2) if total_revenue else 0,
        "current_stock": product.current_stock,
    }

    return render_template(
        "reports/product_detail.html",
        product=product, summary=summary,
        time_series=time_series, contact_rows=contact_rows, item_rows=item_rows,
        date_from=date_from, date_to=date_to, group_by=group_by,
    )


@reports_bp.route("/product/<int:product_id>")
@login_required
def product_detail(product_id):
    return _product_detail(product_id)


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

    by_supplier = defaultdict(lambda: {"id": None, "name": "Unknown", "count": 0, "total": 0.0})
    for p in purchases:
        key = p.supplier_id or 0
        by_supplier[key]["id"] = p.supplier_id
        by_supplier[key]["name"] = p.supplier.name if p.supplier else "Unknown"
        by_supplier[key]["count"] += 1
        by_supplier[key]["total"] += p.total

    rows = sorted(by_supplier.values(), key=lambda v: v["total"], reverse=True)

    return render_template(
        "reports/supplier_summary.html", rows=rows, date_from=date_from, date_to=date_to
    )


@reports_bp.route("/supplier/<int:supplier_id>")
@login_required
def supplier_detail(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    date_from, date_to = _date_range_args()
    group_by = request.args.get("group", "day")
    if group_by not in ("day", "week"):
        group_by = "day"

    purchases = (
        Purchase.query.filter(
            Purchase.supplier_id == supplier_id, Purchase.date >= date_from, Purchase.date <= date_to
        )
        .order_by(Purchase.date.asc(), Purchase.id.asc())
        .all()
    )

    by_period = defaultdict(lambda: {"count": 0, "total": 0.0})
    by_product = defaultdict(lambda: {"qty": 0, "spend": 0.0, "discount_amount": 0.0, "mrp_total": 0.0})
    item_rows = []
    total_spend = 0.0
    total_discount = 0.0
    total_mrp = 0.0

    for p in purchases:
        period = _period_label(p.date, group_by)
        by_period[period]["count"] += 1
        by_period[period]["total"] += p.total

        for item in p.items:
            mrp = item.effective_mrp or 0
            line_spend = item.total
            line_discount = round((mrp - item.purchase_price) * item.qty, 2) if mrp else 0
            product_key = f"{item.product.part_no} - {item.product.product_name}"

            item_rows.append({
                "date": p.date, "purchase_id": p.id, "invoice_no": p.invoice_no,
                "product_name": product_key, "qty": item.qty, "mrp": mrp,
                "discount_pct": item.discount_pct, "price": item.purchase_price,
                "line_total": line_spend,
            })

            by_product[product_key]["qty"] += item.qty
            by_product[product_key]["spend"] += line_spend
            by_product[product_key]["discount_amount"] += line_discount
            by_product[product_key]["mrp_total"] += mrp * item.qty

            total_spend += line_spend
            total_discount += line_discount
            total_mrp += mrp * item.qty

    time_series = sorted(by_period.items(), key=lambda kv: kv[0])
    item_rows.sort(key=lambda r: (r["date"], r["purchase_id"]), reverse=True)

    product_rows = []
    for name, v in by_product.items():
        avg_discount_pct = round(v["discount_amount"] / v["mrp_total"] * 100, 2) if v["mrp_total"] else 0
        product_rows.append({
            "name": name, "qty": v["qty"], "spend": round(v["spend"], 2),
            "discount_amount": round(v["discount_amount"], 2), "avg_discount_pct": avg_discount_pct,
        })
    product_rows.sort(key=lambda r: r["spend"], reverse=True)

    summary = {
        "purchases": len(purchases),
        "total_spend": round(total_spend, 2),
        "total_discount": round(total_discount, 2),
        "avg_discount_pct": round(total_discount / total_mrp * 100, 2) if total_mrp else 0,
    }

    return render_template(
        "reports/supplier_detail.html",
        supplier=supplier, summary=summary,
        time_series=time_series, product_rows=product_rows, item_rows=item_rows,
        date_from=date_from, date_to=date_to, group_by=group_by,
    )


@reports_bp.route("/brand-wise")
@login_required
def brand_wise():
    date_from, date_to = _date_range_args()
    items = (
        SaleItem.query.join(Sale)
        .filter(Sale.date >= date_from, Sale.date <= date_to)
        .all()
    )

    by_brand = defaultdict(lambda: {"id": None, "name": "No brand", "qty": 0, "revenue": 0.0})
    for item in items:
        brand = item.product.brand
        key = brand.id if brand else 0
        by_brand[key]["id"] = brand.id if brand else None
        by_brand[key]["name"] = brand.name if brand else "No brand"
        by_brand[key]["qty"] += item.qty
        by_brand[key]["revenue"] += item.line_total

    rows = sorted(by_brand.values(), key=lambda v: v["revenue"], reverse=True)

    return render_template(
        "reports/brand_wise.html", rows=rows, date_from=date_from, date_to=date_to
    )


@reports_bp.route("/brand/<int:brand_id>")
@login_required
def brand_detail(brand_id):
    brand = Brand.query.get_or_404(brand_id)
    date_from, date_to = _date_range_args()
    group_by = request.args.get("group", "day")
    if group_by not in ("day", "week"):
        group_by = "day"

    items = (
        SaleItem.query.join(Sale).join(Product)
        .filter(Product.brand_id == brand_id, Sale.date >= date_from, Sale.date <= date_to)
        .order_by(Sale.date.asc(), Sale.id.asc())
        .all()
    )

    by_period = defaultdict(lambda: {"count": 0, "revenue": 0.0})
    by_product = defaultdict(lambda: {"qty": 0, "revenue": 0.0, "cost": 0.0, "discount_amount": 0.0, "mrp_total": 0.0})
    item_rows = []
    total_revenue = 0.0
    total_cost = 0.0
    total_discount = 0.0
    total_mrp = 0.0
    total_qty = 0

    for item in items:
        s = item.sale
        period = _period_label(s.date, group_by)
        by_period[period]["count"] += 1
        by_period[period]["revenue"] += item.line_total

        mrp = item.mrp_at_sale or 0
        unit_cost = (
            item.purchase_item.purchase_price if item.purchase_item
            else (item.product.actual_discounted_price or 0)
        )
        line_revenue = item.line_total
        line_cost = round(item.qty * unit_cost, 2)
        line_discount = round((mrp - item.selling_price) * item.qty, 2) if mrp else 0
        product_key = f"{item.product.part_no} - {item.product.product_name}"

        item_rows.append({
            "date": s.date, "sale_id": s.id, "invoice_no": s.invoice_no,
            "product_name": product_key, "qty": item.qty, "mrp": mrp,
            "discount_pct": item.discount_pct, "price": item.selling_price,
            "line_total": line_revenue,
        })

        by_product[product_key]["qty"] += item.qty
        by_product[product_key]["revenue"] += line_revenue
        by_product[product_key]["cost"] += line_cost
        by_product[product_key]["discount_amount"] += line_discount
        by_product[product_key]["mrp_total"] += mrp * item.qty

        total_revenue += line_revenue
        total_cost += line_cost
        total_discount += line_discount
        total_mrp += mrp * item.qty
        total_qty += item.qty

    time_series = sorted(by_period.items(), key=lambda kv: kv[0])
    item_rows.sort(key=lambda r: (r["date"], r["sale_id"]), reverse=True)

    product_rows = []
    for name, v in by_product.items():
        profit = round(v["revenue"] - v["cost"], 2)
        profit_pct = round(profit / v["revenue"] * 100, 2) if v["revenue"] else 0
        avg_discount_pct = round(v["discount_amount"] / v["mrp_total"] * 100, 2) if v["mrp_total"] else 0
        product_rows.append({
            "name": name, "qty": v["qty"], "revenue": round(v["revenue"], 2),
            "discount_amount": round(v["discount_amount"], 2), "avg_discount_pct": avg_discount_pct,
            "profit": profit, "profit_pct": profit_pct,
        })
    product_rows.sort(key=lambda r: r["revenue"], reverse=True)

    products = Product.query.filter(Product.brand_id == brand_id).order_by(Product.product_name.asc()).all()
    stock_value = round(sum((p.actual_discounted_price or 0) * (p.current_stock or 0) for p in products), 2)

    total_profit = round(total_revenue - total_cost, 2)
    summary = {
        "qty_sold": total_qty,
        "total_revenue": round(total_revenue, 2),
        "total_discount": round(total_discount, 2),
        "avg_discount_pct": round(total_discount / total_mrp * 100, 2) if total_mrp else 0,
        "total_cost": round(total_cost, 2),
        "total_profit": total_profit,
        "profit_pct": round(total_profit / total_revenue * 100, 2) if total_revenue else 0,
        "product_count": len(products),
        "stock_value": stock_value,
    }

    return render_template(
        "reports/brand_detail.html",
        brand=brand, summary=summary, products=products,
        time_series=time_series, product_rows=product_rows, item_rows=item_rows,
        date_from=date_from, date_to=date_to, group_by=group_by,
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
