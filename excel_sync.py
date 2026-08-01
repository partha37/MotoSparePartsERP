"""Mirrors the SQLite data into a single Excel workbook (instance/erp_data.xlsx).

Call sync_to_excel() right after any db.session.commit() that adds, edits, or
deletes a row. It re-reads every table from the DB and rewrites the workbook,
so the two are always consistent with each other — there's no incremental
diffing to get wrong. The workbook is a read-only mirror for the shop owner
to browse/filter in Excel; the database remains the single source of truth.

Writing is best-effort: if erp_data.xlsx is currently open in Excel (locked
on Windows) or anything else goes wrong, the DB write already succeeded, so
we just flash a warning instead of failing the request.
"""

import os

from flask import current_app, flash
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from models import (
    Product, Supplier, Customer, Mechanic,
    Purchase, PurchaseItem, Sale, SaleItem, StockMovement, ShopSettings,
)

EXCEL_FILENAME = "erp_data.xlsx"

# sheet_name -> (model, [column headers])
# Columns that aren't plain model attributes (e.g. "supplier_name") are
# resolved by _cell_value below.
SHEETS = {
    "Products": (Product, [
        "id", "part_no", "product_name", "brand", "category", "vehicle_name", "unit", "hsn_code",
        "gst_rate", "mrp", "actual_discount_pct", "actual_discounted_price",
        "margin_per_unit", "current_stock", "reorder_level",
    ]),
    "Suppliers": (Supplier, ["id", "name", "brand", "phone", "address", "gstin"]),
    "Customers": (Customer, ["id", "name", "phone", "address", "vehicle_model", "discount_pct"]),
    "Mechanics": (Mechanic, ["id", "name", "phone", "garage_name", "discount_pct"]),
    "Purchases": (Purchase, [
        "id", "date", "invoice_no", "supplier_id", "supplier_name", "total",
    ]),
    "PurchaseItems": (PurchaseItem, [
        "id", "purchase_id", "product_id", "product_name", "qty", "purchase_price",
        "mrp_at_purchase", "remaining_qty", "stock_number", "total",
    ]),
    "Sales": (Sale, [
        "id", "date", "invoice_no", "customer_id", "customer_name", "mechanic_id",
        "mechanic_name", "payment_mode", "amount_paid", "total", "balance_due",
    ]),
    "SaleItems": (SaleItem, [
        "id", "sale_id", "product_id", "product_name", "qty", "selling_price",
        "purchase_item_id", "line_total",
    ]),
    "StockMovements": (StockMovement, [
        "id", "date", "product_id", "product_name", "type", "qty",
        "reference_type", "reference_id", "note",
    ]),
}

_DERIVED = {
    "supplier_name": lambda row: row.supplier.name if row.supplier else "",
    "customer_name": lambda row: row.customer.name if row.customer else "Walk-in",
    "mechanic_name": lambda row: row.mechanic.name if row.mechanic else "",
    "product_name": lambda row: row.product.product_name if row.product else "",
}


_MISSING = object()


def _cell_value(row, col):
    value = getattr(row, col, _MISSING)
    if value is not _MISSING:
        return value
    if col in _DERIVED:
        return _DERIVED[col](row)
    return ""


def _autofit(ws):
    for col_cells in ws.columns:
        length = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
        ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max(length + 2, 10), 40)


def excel_path(app=None):
    app = app or current_app._get_current_object()
    return os.path.join(app.instance_path, EXCEL_FILENAME)


def _write_workbook(path):
    wb = Workbook()
    wb.remove(wb.active)

    for sheet_name, (model, columns) in SHEETS.items():
        ws = wb.create_sheet(title=sheet_name)
        ws.append(columns)
        for row in model.query.order_by(model.id.asc()).all():
            ws.append([_cell_value(row, col) for col in columns])
        _autofit(ws)

    shop = ShopSettings.query.first()
    ws = wb.create_sheet(title="ShopSettings")
    ws.append(["shop_name", "address", "phone", "gstin"])
    if shop:
        ws.append([shop.shop_name, shop.address, shop.phone, shop.gstin])
    _autofit(ws)

    tmp_path = path + ".tmp"
    wb.save(tmp_path)
    os.replace(tmp_path, path)


def sync_to_excel():
    """Rewrite instance/erp_data.xlsx from the current DB state. Never raises."""
    path = excel_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _write_workbook(path)
    except PermissionError:
        flash(
            "Saved to the database, but erp_data.xlsx is open elsewhere (e.g. Excel) "
            "so the Excel mirror couldn't be updated. It will catch up on the next change.",
            "warning",
        )
    except Exception:
        current_app.logger.exception("Excel sync failed")
        flash("Saved to the database, but updating the Excel mirror failed.", "warning")
