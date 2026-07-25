from datetime import datetime, date

from flask_login import UserMixin

from extensions import db


class User(UserMixin, db.Model):
    """Single shop-owner login account."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class ShopSettings(db.Model):
    """Single-row table holding shop info used on invoices."""

    id = db.Column(db.Integer, primary_key=True)
    shop_name = db.Column(db.String(150), default="")
    address = db.Column(db.String(255), default="")
    phone = db.Column(db.String(20), default="")
    gstin = db.Column(db.String(20), default="")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(150), nullable=False)
    part_no = db.Column(db.String(80), unique=True, nullable=False, index=True)
    brand = db.Column(db.String(50))
    category = db.Column(db.String(80))
    unit = db.Column(db.String(20), default="pc")
    hsn_code = db.Column(db.String(20))
    gst_rate = db.Column(db.Float, default=18.0)

    mrp = db.Column(db.Float, nullable=False, default=0)
    actual_discount_pct = db.Column(db.Float, default=0)
    actual_discounted_price = db.Column(db.Float, default=0)
    selling_discount_pct = db.Column(db.Float, default=0)
    mrp_discounted_price = db.Column(db.Float, default=0)

    current_stock = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=5)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def recalc_prices(self):
        self.actual_discounted_price = round(
            self.mrp * (1 - (self.actual_discount_pct or 0) / 100), 2
        )
        self.mrp_discounted_price = round(
            self.mrp * (1 - (self.selling_discount_pct or 0) / 100), 2
        )

    @property
    def margin_per_unit(self):
        return round((self.mrp_discounted_price or 0) - (self.actual_discounted_price or 0), 2)

    @property
    def is_low_stock(self):
        return self.current_stock <= self.reorder_level

    def __repr__(self):
        return f"<Product {self.part_no} {self.product_name}>"


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    brand = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    gstin = db.Column(db.String(20))

    purchases = db.relationship("Purchase", backref="supplier", lazy=True)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    vehicle_model = db.Column(db.String(100))

    sales = db.relationship("Sale", backref="customer", lazy=True)


class Mechanic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20))
    garage_name = db.Column(db.String(150))
    commission_pct = db.Column(db.Float, default=0)

    sales = db.relationship("Sale", backref="mechanic", lazy=True)


class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)
    invoice_no = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship(
        "PurchaseItem", backref="purchase", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def total(self):
        return round(sum(item.total for item in self.items), 2)


class PurchaseItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchase.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)

    product = db.relationship("Product")

    @property
    def total(self):
        return round(self.qty * self.purchase_price, 2)


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(50), unique=True)
    date = db.Column(db.Date, default=date.today, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=True)
    mechanic_id = db.Column(db.Integer, db.ForeignKey("mechanic.id"), nullable=True)
    payment_mode = db.Column(db.String(20), default="cash")
    amount_paid = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship(
        "SaleItem", backref="sale", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def subtotal(self):
        return round(sum(item.qty * item.selling_price for item in self.items), 2)

    @property
    def gst_amount(self):
        return round(sum(item.gst_amount for item in self.items), 2)

    @property
    def total(self):
        return round(self.subtotal + self.gst_amount, 2)

    @property
    def balance_due(self):
        return round(self.total - (self.amount_paid or 0), 2)


class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    selling_price = db.Column(db.Float, nullable=False)
    gst_rate = db.Column(db.Float, default=0)

    product = db.relationship("Product")

    @property
    def line_subtotal(self):
        return round(self.qty * self.selling_price, 2)

    @property
    def gst_amount(self):
        return round(self.line_subtotal * (self.gst_rate or 0) / 100, 2)

    @property
    def line_total(self):
        return round(self.line_subtotal + self.gst_amount, 2)


class StockMovement(db.Model):
    """Every purchase and sale writes a row here — powers day-wise tracking."""

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # purchase_in, sale_out, adjustment, return
    qty = db.Column(db.Integer, nullable=False)  # positive for in, negative for out
    reference_type = db.Column(db.String(20))  # "purchase" / "sale" / "adjustment"
    reference_id = db.Column(db.Integer)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product")
