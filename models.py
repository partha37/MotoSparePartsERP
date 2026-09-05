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


class ProductCategory(db.Model):
    """Shared master list of product categories (Electrical, Fiber, ...). A product
    in one of these uses its Customer/Mechanic category rate instead of the brand
    rate at checkout; a product with no category is "Normal" and uses the brand rate,
    so "Normal" is deliberately not a row here."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(150), nullable=False)
    part_no = db.Column(db.String(80), unique=True, nullable=False, index=True)
    brand_id = db.Column(db.Integer, db.ForeignKey("brand.id"), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("product_category.id"), nullable=True)
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
    category = db.relationship("ProductCategory", backref="products")

    def recalc_prices(self):
        """Recomputes cost price only — selling price is decided per-sale at checkout, not stored here."""
        self.actual_discounted_price = round(
            self.mrp * (1 - (self.actual_discount_pct or 0) / 100), 2
        )

    def update_cost_from_purchase(self, purchase_price, new_mrp=None, gst_rate=None):
        """Makes this purchase's price the product's new current cost; optionally updates MRP too
        (e.g. the distributor revised the printed MRP) and the product's reference GST rate.
        Each purchase still keeps its own price/rate on PurchaseItem — this only updates the
        product's "current" reference fields. purchase_price is GST-inclusive — that's the real
        cost being compared against MRP here, not what the supplier quoted before tax."""
        if new_mrp is not None and new_mrp > 0:
            self.mrp = new_mrp
        if gst_rate is not None:
            self.gst_rate = gst_rate
        self.actual_discount_pct = (
            (self.mrp - purchase_price) / self.mrp * 100 if self.mrp else 0
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

    @property
    def category_name(self):
        return self.category.name if self.category else ""

    def __repr__(self):
        return f"<Product {self.part_no} {self.product_name}>"


supplier_brand = db.Table(
    "supplier_brand",
    db.Column("supplier_id", db.Integer, db.ForeignKey("supplier.id"), primary_key=True),
    db.Column("brand_id", db.Integer, db.ForeignKey("brand.id"), primary_key=True),
)


class Supplier(db.Model):
    """A supplier can carry more than one brand (e.g. a distributor selling
    both Honda and Bajaj parts), so brands is many-to-many rather than the
    single brand_id every other brand-linked model uses."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    gstin = db.Column(db.String(20))

    purchases = db.relationship("Purchase", backref="supplier", lazy=True)
    brands = db.relationship("Brand", secondary=supplier_brand, backref="suppliers", order_by="Brand.name")

    @property
    def brand_names(self):
        return ", ".join(b.name for b in self.brands)


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

    def discount_for_product(self, brand_id, category_id):
        """The rate actually applied at checkout: this customer's brand rate, plus
        the brand+category adjustment when one is set for the product's pair (e.g.
        Tvs 13% + Fiber -2% = 11%). No pair set means no adjustment, so the plain
        brand rate stands."""
        base = self.discount_for_brand(brand_id)
        for cd in self.category_discounts:
            if cd.brand_id == brand_id and cd.category_id == category_id:
                return round(base + (cd.discount_pct or 0), 2)
        return base


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


class CustomerCategoryDiscount(db.Model):
    """One rate per customer + brand + category (e.g. "Honda Fiber 25%") — the
    category rate is brand-specific, since the same category is worth a different
    discount across brands."""

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey("brand.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("product_category.id"), nullable=False)
    discount_pct = db.Column(db.Float, default=0)

    customer = db.relationship(
        "Customer",
        backref=db.backref("category_discounts", cascade="all, delete-orphan"),
    )
    brand = db.relationship("Brand")
    category = db.relationship("ProductCategory")

    @property
    def customer_name(self):
        return self.customer.name if self.customer else ""

    @property
    def brand_name(self):
        return self.brand.name if self.brand else ""

    @property
    def category_name(self):
        return self.category.name if self.category else ""


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

    def discount_for_product(self, brand_id, category_id):
        """The rate actually applied at checkout: this mechanic's brand rate, plus
        the brand+category adjustment when one is set for the product's pair —
        see Customer.discount_for_product."""
        base = self.discount_for_brand(brand_id)
        for cd in self.category_discounts:
            if cd.brand_id == brand_id and cd.category_id == category_id:
                return round(base + (cd.discount_pct or 0), 2)
        return base


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


class MechanicCategoryDiscount(db.Model):
    """One rate per mechanic + brand + category — see CustomerCategoryDiscount."""

    id = db.Column(db.Integer, primary_key=True)
    mechanic_id = db.Column(db.Integer, db.ForeignKey("mechanic.id"), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey("brand.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("product_category.id"), nullable=False)
    discount_pct = db.Column(db.Float, default=0)

    mechanic = db.relationship(
        "Mechanic",
        backref=db.backref("category_discounts", cascade="all, delete-orphan"),
    )
    brand = db.relationship("Brand")
    category = db.relationship("ProductCategory")

    @property
    def mechanic_name(self):
        return self.mechanic.name if self.mechanic else ""

    @property
    def brand_name(self):
        return self.brand.name if self.brand else ""

    @property
    def category_name(self):
        return self.category.name if self.category else ""


class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)
    invoice_no = db.Column(db.String(50))
    delivery_charge = db.Column(db.Float, default=0)  # single fixed-label extra charge, always available
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship(
        "PurchaseItem", backref="purchase", lazy=True, cascade="all, delete-orphan"
    )
    charges = db.relationship(
        "PurchaseCharge", backref="purchase", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def items_total(self):
        """Goods-only subtotal — what the stock itself cost, before delivery/incidental charges."""
        return round(sum(item.total for item in self.items), 2)

    @property
    def charges_total(self):
        """Delivery charge plus every free-form extra charge (round off, handling, etc.)."""
        return round((self.delivery_charge or 0) + sum(c.amount for c in self.charges), 2)

    @property
    def total(self):
        """The actual amount payable on this purchase — items_total + charges_total. Existing
        purchases (recorded before this feature existed) have no delivery_charge/charges rows,
        so this is numerically identical to the old items-only total for them."""
        return round(self.items_total + self.charges_total, 2)

    @property
    def gst_total(self):
        return round(sum(item.gst_amount for item in self.items), 2)

    @property
    def pre_gst_total(self):
        return round(sum((item.price_before_gst or 0) * item.qty for item in self.items), 2)

    @property
    def is_editable(self):
        """True only for the single most-recently-created Purchase, and only
        while none of its batches have been drawn from yet — editing needs to
        reverse this purchase's stock effects (see
        routes/purchases.py::edit_purchase), but a SaleItem already pointing
        at one of its PurchaseItem rows means real stock has left on this
        exact batch, and Product.current_stock can no longer be safely
        unwound to "as if this purchase never happened"."""
        last = Purchase.query.order_by(Purchase.id.desc()).first()
        if not last or last.id != self.id:
            return False
        batch_ids = [item.id for item in self.items]
        if batch_ids and SaleItem.query.filter(SaleItem.purchase_item_id.in_(batch_ids)).first():
            return False
        return True


class PurchaseCharge(db.Model):
    """A free-form extra line on a purchase invoice that isn't tied to any product —
    round-off, incidental charges, stock handling charges, etc. Distinct from
    Purchase.delivery_charge, which is a single always-available fixed-label field."""
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchase.id"), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)


class PurchaseItem(db.Model):
    """Also doubles as a sellable stock batch: `remaining_qty` tracks how much of this
    specific purchase is still in stock, so a sale can draw from a particular batch and use
    that batch's own MRP rather than the product's blended "current" MRP."""

    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchase.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)  # GST-inclusive — the real per-unit cost of this batch
    price_before_gst = db.Column(db.Float)  # what the supplier actually quoted, before GST — null for pre-GST-tracking rows
    gst_rate = db.Column(db.Float)  # GST% used for this line, snapshot at purchase time — null for pre-GST-tracking rows
    mrp_at_purchase = db.Column(db.Float)  # snapshot of the MRP that was in effect for this purchase
    remaining_qty = db.Column(db.Integer)  # how much of this batch hasn't been sold yet

    product = db.relationship("Product", backref="purchase_items")

    @property
    def total(self):
        return round(self.qty * self.purchase_price, 2)

    @property
    def gst_amount_per_unit(self):
        """GST paid per unit — purchase_price is GST-inclusive, price_before_gst isn't,
        so the difference is exactly the tax. 0 for rows recorded before GST tracking
        existed (price_before_gst is null, meaning purchase_price was entered pre-GST
        with no tax added on top)."""
        if self.price_before_gst is None:
            return 0
        return round(self.purchase_price - self.price_before_gst, 2)

    @property
    def gst_amount(self):
        return round(self.gst_amount_per_unit * self.qty, 2)

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
    # True only when the "Walk-in" option was explicitly chosen at checkout;
    # False + customer_id None means "-- None --" was left/chosen instead —
    # both display as no linked Customer record, but customer_display below
    # tells them apart. Existing rows predate this distinction entirely, so
    # they default to True (Walk-in) via the migration's server_default —
    # matching how every one of them already displayed before this column
    # existed, with no separate backfill needed.
    is_walkin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship(
        "SaleItem", backref="sale", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def customer_display(self):
        if self.customer:
            return self.customer.name
        return "Walk-in" if self.is_walkin else "-"

    @property
    def total(self):
        """What the customer pays. MRP already includes GST, so this is not added on top of it."""
        return round(sum(item.line_total for item in self.items), 2)

    @property
    def amount_paid(self):
        """Sum of all Payment rows against this sale — see the Payment model."""
        return round(sum(p.amount for p in self.payments), 2)

    @property
    def return_credit(self):
        """Total refund value counting toward this sale's balance: its own
        standalone returns, plus any returns from a *different* sale that were
        applied here via the exchange flow (SaleReturn.applied_to_sale_id) —
        see SaleReturn for why a return can credit a sale other than the one
        the returned items were originally bought on."""
        own = sum(r.refund_amount for r in self.returns if r.applied_to_sale_id is None)
        applied = sum(r.refund_amount for r in self.applied_returns)
        return round(own + applied, 2)

    @property
    def net_total(self):
        """Total after netting out returned quantities — what reports use so
        revenue/profit aren't overstated after a return. Sale.total itself stays
        the original, historical invoice amount and is never rewritten."""
        return round(sum(item.net_line_total for item in self.items), 2)

    @property
    def balance_due(self):
        """Can go negative — that means a refund is owed back to the customer
        (e.g. they'd already paid in full before returning something)."""
        return round(self.total - self.amount_paid - self.return_credit, 2)

    @property
    def is_editable(self):
        """True only for the single most-recently-created Sale, and only
        while nothing downstream has been recorded against it yet — a
        return/exchange, or more than the one checkout-time Payment. Editing
        needs to safely reverse and redo this sale's stock/payment side
        effects (see routes/sales.py::edit_sale); anything beyond that single
        initial Payment (a later installment, a refund) would mean real cash
        history gets silently destroyed by an edit, so it's blocked instead."""
        last = Sale.query.order_by(Sale.id.desc()).first()
        if not last or last.id != self.id:
            return False
        if SaleReturn.query.filter(
            (SaleReturn.sale_id == self.id) | (SaleReturn.applied_to_sale_id == self.id)
        ).first():
            return False
        if len(self.payments) > 1 or (self.payments and self.payments[0].amount < 0):
            return False
        return True


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

    @property
    def returned_qty(self):
        """Total qty returned against this line so far, across all SaleReturns
        (both resellable and defective — either way the customer no longer has it)."""
        return sum(ri.qty for ri in self.return_items)

    @property
    def returnable_qty(self):
        return max(0, self.qty - self.returned_qty)

    @property
    def net_qty(self):
        """Qty actually kept by the customer after returns — what reports should
        count as "sold", so revenue/profit don't stay overstated after a return."""
        return self.qty - self.returned_qty

    @property
    def net_line_total(self):
        return round(self.net_qty * self.selling_price, 2)


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


class SaleReturn(db.Model):
    """A customer/mechanic return against a sale — either handed back because
    they didn't want it (resellable, restocked) or because it was defective
    (removed from the customer but not restocked). See SaleReturnItem for the
    per-line condition and stock handling.

    `sale_id` is always the *original* sale the returned items were bought on
    (needed to validate which SaleItems can be returned). `applied_to_sale_id`
    is set only by the combined return+new-sale "exchange" flow, when the
    refund is used toward a *different*, newly-created sale in the same visit
    instead of being left as a standalone credit/refund against the original
    sale — see Sale.return_credit for how the two cases are told apart."""

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=False)
    applied_to_sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=True)
    return_no = db.Column(db.String(50), unique=True)
    date = db.Column(db.Date, default=date.today, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.String(255))

    sale = db.relationship(
        "Sale", foreign_keys=[sale_id],
        backref=db.backref("returns", order_by="SaleReturn.date, SaleReturn.id"),
    )
    applied_to_sale = db.relationship("Sale", foreign_keys=[applied_to_sale_id], backref="applied_returns")
    items = db.relationship("SaleReturnItem", backref="sale_return", lazy=True, cascade="all, delete-orphan")

    @property
    def refund_amount(self):
        return round(sum(i.refund_amount for i in self.items), 2)

    @property
    def invoice_no(self):
        return self.sale.invoice_no if self.sale else ""


class SaleReturnItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_return_id = db.Column(db.Integer, db.ForeignKey("sale_return.id"), nullable=False)
    sale_item_id = db.Column(db.Integer, db.ForeignKey("sale_item.id"), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    condition = db.Column(db.String(20), nullable=False)  # 'resellable' or 'defective'

    sale_item = db.relationship("SaleItem", backref=db.backref("return_items", lazy=True))

    @property
    def refund_amount(self):
        return round(self.qty * self.sale_item.selling_price, 2)

    @property
    def product(self):
        return self.sale_item.product if self.sale_item else None


class StockMovement(db.Model):
    """Every purchase and sale writes a row here — powers day-wise tracking."""

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # purchase_in, sale_out, adjustment, return
    qty = db.Column(db.Integer, nullable=False)  # positive for in, negative for out
    reference_type = db.Column(db.String(20))  # "purchase" / "sale" / "adjustment" / "sale_return"
    reference_id = db.Column(db.Integer)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product")
