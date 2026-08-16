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


class Brand(db.Model):
    """Shared master list of brands (Honda, TVS, Bajaj, Universal, ...) used
    consistently across Products, Suppliers, and Customer/Mechanic brand-wise
    discounts, instead of free-typed text scattered across each of them."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(150), nullable=False)
    part_no = db.Column(db.String(80), unique=True, nullable=False, index=True)
    brand_id = db.Column(db.Integer, db.ForeignKey("brand.id"), nullable=True)
    category = db.Column(db.String(80))
    vehicle_name = db.Column(db.String(150))  # vehicle model(s) this part fits, e.g. "Honda Activa"
    unit = db.Column(db.String(20), default="pc")
    hsn_code = db.Column(db.String(20))
    gst_rate = db.Column(db.Float, default=18.0)

    mrp = db.Column(db.Float, nullable=False, default=0)
    actual_discount_pct = db.Column(db.Float, default=0)
    actual_discounted_price = db.Column(db.Float, default=0)

    current_stock = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=5)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    brand = db.relationship("Brand", backref="products")

    def recalc_prices(self):
        """Recomputes cost price only — selling price is decided per-sale at checkout, not stored here."""
        self.actual_discounted_price = round(
            self.mrp * (1 - (self.actual_discount_pct or 0) / 100), 2
        )

    def update_cost_from_purchase(self, purchase_price, new_mrp=None):
        """Makes this purchase's price the product's new current cost; optionally updates MRP too
        (e.g. the distributor revised the printed MRP). Each purchase still keeps its own price on
        PurchaseItem — this only updates the product's "current" reference fields."""
        if new_mrp is not None and new_mrp > 0:
            self.mrp = new_mrp
        self.actual_discount_pct = (
            round((self.mrp - purchase_price) / self.mrp * 100, 2) if self.mrp else 0
        )
        self.recalc_prices()

    @property
    def margin_per_unit(self):
        """Best-case margin if sold at full MRP — actual margin depends on the price/discount used at checkout."""
        return round((self.mrp or 0) - (self.actual_discounted_price or 0), 2)

    @property
    def is_low_stock(self):
        return self.current_stock <= self.reorder_level

    @property
    def brand_name(self):
        return self.brand.name if self.brand else ""

    def __repr__(self):
        return f"<Product {self.part_no} {self.product_name}>"


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey("brand.id"), nullable=True)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    gstin = db.Column(db.String(20))

    purchases = db.relationship("Purchase", backref="supplier", lazy=True)
    brand = db.relationship("Brand", backref="suppliers")

    @property
    def brand_name(self):
        return self.brand.name if self.brand else ""


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    vehicle_model = db.Column(db.String(100))

    sales = db.relationship("Sale", backref="customer", lazy=True)

    def discount_for_brand(self, brand_id):
        """Standing discount off MRP for a given product brand, auto-applied at checkout."""
        if not brand_id:
            return 0
        for bd in self.brand_discounts:
            if bd.brand_id == brand_id:
                return bd.discount_pct or 0
        return 0


class CustomerBrandDiscount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey("brand.id"), nullable=False)
    discount_pct = db.Column(db.Float, default=0)

    customer = db.relationship(
        "Customer",
        backref=db.backref("brand_discounts", cascade="all, delete-orphan"),
    )
    brand = db.relationship("Brand")

    @property
    def customer_name(self):
        return self.customer.name if self.customer else ""

    @property
    def brand_name(self):
        return self.brand.name if self.brand else ""


class Mechanic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20))
    garage_name = db.Column(db.String(150))

    sales = db.relationship("Sale", backref="mechanic", lazy=True)

    def discount_for_brand(self, brand_id):
        """Standing discount for customers this mechanic refers, per product brand."""
        if not brand_id:
            return 0
        for bd in self.brand_discounts:
            if bd.brand_id == brand_id:
                return bd.discount_pct or 0
        return 0


class MechanicBrandDiscount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mechanic_id = db.Column(db.Integer, db.ForeignKey("mechanic.id"), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey("brand.id"), nullable=False)
    discount_pct = db.Column(db.Float, default=0)

    mechanic = db.relationship(
        "Mechanic",
        backref=db.backref("brand_discounts", cascade="all, delete-orphan"),
    )
    brand = db.relationship("Brand")

    @property
    def mechanic_name(self):
        return self.mechanic.name if self.mechanic else ""

    @property
    def brand_name(self):
        return self.brand.name if self.brand else ""


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
    """Also doubles as a sellable stock batch: `remaining_qty` tracks how much of this
    specific purchase is still in stock, so a sale can draw from a particular batch and use
    that batch's own MRP rather than the product's blended "current" MRP."""

    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchase.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    mrp_at_purchase = db.Column(db.Float)  # snapshot of the MRP that was in effect for this purchase
    remaining_qty = db.Column(db.Integer)  # how much of this batch hasn't been sold yet

    product = db.relationship("Product", backref="purchase_items")

    @property
    def total(self):
        return round(self.qty * self.purchase_price, 2)

    @property
    def stock_number(self):
        """A date-based batch label, e.g. 26072026-14, unique via the row id suffix."""
        return f"{self.purchase.date.strftime('%d%m%Y')}-{self.id}"

    @property
    def effective_mrp(self):
        """MRP to charge for this batch — falls back to the product's current MRP for
        batches recorded before mrp_at_purchase existed."""
        return self.mrp_at_purchase if self.mrp_at_purchase is not None else self.product.mrp

    @property
    def discount_pct(self):
        """Discount off MRP this batch was bought at — same formula as
        Product.update_cost_from_purchase uses for the product's headline
        discount, just scoped to this specific batch's own numbers."""
        mrp = self.effective_mrp
        if not mrp:
            return 0
        return round((1 - self.purchase_price / mrp) * 100, 2)


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(50), unique=True)
    date = db.Column(db.Date, default=date.today, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=True)
    mechanic_id = db.Column(db.Integer, db.ForeignKey("mechanic.id"), nullable=True)
    payment_mode = db.Column(db.String(20), default="cash")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship(
        "SaleItem", backref="sale", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def total(self):
        """What the customer pays. MRP already includes GST, so this is not added on top of it."""
        return round(sum(item.line_total for item in self.items), 2)

    @property
    def amount_paid(self):
        """Sum of all Payment rows against this sale — see the Payment model."""
        return round(sum(p.amount for p in self.payments), 2)

    @property
    def balance_due(self):
        return round(self.total - self.amount_paid, 2)


class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    selling_price = db.Column(db.Float, nullable=False)
    purchase_item_id = db.Column(db.Integer, db.ForeignKey("purchase_item.id"), nullable=True)

    product = db.relationship("Product")
    purchase_item = db.relationship("PurchaseItem")

    @property
    def line_total(self):
        return round(self.qty * self.selling_price, 2)

    @property
    def mrp_at_sale(self):
        """The batch's MRP at time of sale — falls back to the product's
        current MRP only for legacy sales made before batch tracking existed
        (purchase_item_id is None), same fallback rule as the profit-margin
        report uses for cost."""
        if self.purchase_item:
            return self.purchase_item.effective_mrp
        return self.product.mrp if self.product else 0

    @property
    def discount_pct(self):
        """Discount actually given vs that batch's MRP — derived from
        selling_price rather than stored, since selling_price (entered per
        line at checkout) is the only number actually recorded at sale time."""
        mrp = self.mrp_at_sale
        if not mrp:
            return 0
        return round((1 - self.selling_price / mrp) * 100, 2)


class Payment(db.Model):
    """A single installment paid against a Sale's balance due."""

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(20), default="cash")
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sale = db.relationship(
        "Sale", backref=db.backref("payments", order_by="Payment.date, Payment.id")
    )

    @property
    def invoice_no(self):
        return self.sale.invoice_no if self.sale else ""


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
