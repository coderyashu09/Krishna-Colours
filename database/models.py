"""
SQLAlchemy ORM models for Krishna Colour – Asian Paints Customer Management System.
Supports PostgreSQL (Supabase Cloud) and SQLite with strict relational integrity,
Decimal monetary precision, multiple bills per customer, dual item entry (dropdown + custom),
and Final Deal Amount payment tracking (without bargain remaining balance).
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Boolean,
    DateTime, Date, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Authorized system user (Admin / Staff)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False, default="admin")  # 'admin' or 'staff'
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ItemCategory(Base):
    """Admin-managed paint categories for the item selection dropdown."""
    __tablename__ = "item_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    products = relationship(
        "ItemProduct",
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="ItemProduct.id.asc()",
    )


class ItemProduct(Base):
    """Admin-managed paint products belonging to a category."""
    __tablename__ = "item_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("item_categories.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_category_product_name"),
    )

    category = relationship("ItemCategory", back_populates="products")
    pack_sizes = relationship(
        "ItemPackSize",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ItemPackSize.sort_order.asc(), ItemPackSize.id.asc()",
    )


class ItemPackSize(Base):
    """Admin-managed pack sizes for a product (e.g., 1 L, 4 L, 10 L, 20 L)."""
    __tablename__ = "item_pack_sizes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("item_products.id", ondelete="CASCADE"), nullable=False, index=True)
    size_label = Column(String(80), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("product_id", "size_label", name="uq_product_pack_size_label"),
    )

    product = relationship("ItemProduct", back_populates="pack_sizes")


class Customer(Base):
    """Customer directory record with unique KC-XXXXXX ID."""
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_code = Column(String(50), unique=True, nullable=False, index=True)  # KC-000001
    name = Column(String(150), nullable=False, index=True)
    mobile = Column(String(20), nullable=False, index=True)
    address = Column(Text, nullable=False, default="")
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bills = relationship(
        "CustomerBill",
        back_populates="customer",
        cascade="all, delete-orphan",
        order_by="CustomerBill.bill_date.desc(), CustomerBill.id.desc()",
    )
    payments = relationship(
        "BillPayment",
        back_populates="customer",
        cascade="all, delete-orphan",
        order_by="BillPayment.payment_date.desc(), BillPayment.id.desc()",
    )

    @property
    def total_final_deal_amount(self) -> Decimal:
        return sum((b.effective_final_amount for b in self.bills), Decimal("0.00"))

    @property
    def total_amount_received(self) -> Decimal:
        return sum((b.amount_received or Decimal("0.00") for b in self.bills), Decimal("0.00"))

    @property
    def total_pending_amount(self) -> Decimal:
        return sum((b.pending_amount for b in self.bills), Decimal("0.00"))

    @property
    def overall_payment_status(self) -> str:
        return "Payment Pending" if self.total_pending_amount > Decimal("0.00") else "Paid"


class CustomerBill(Base):
    """
    Individual bill record for a customer.
    Only Final Deal Amount and Amount Received are stored.
    Unless `has_pending` is explicitly enabled, Amount Received is the closed final amount
    with zero pending balance. When `has_pending` is enabled, Pending = Final Deal - Received.
    """
    __tablename__ = "customer_bills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    bill_number = Column(String(100), nullable=False, index=True)
    bill_date = Column(Date, default=date.today, nullable=False, index=True)
    final_deal_amount = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    amount_received = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    has_pending = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("customer_id", "bill_number", name="uq_customer_bill_number"),
    )

    customer = relationship("Customer", back_populates="bills")
    items = relationship(
        "BillItem",
        back_populates="bill",
        cascade="all, delete-orphan",
        order_by="BillItem.id.asc()",
    )
    payments = relationship(
        "BillPayment",
        back_populates="bill",
        cascade="all, delete-orphan",
        order_by="BillPayment.payment_date.desc(), BillPayment.id.desc()",
    )

    @property
    def effective_final_amount(self) -> Decimal:
        """If pending tracking is OFF, Amount Received is the final closed amount."""
        if self.has_pending:
            return self.final_deal_amount or Decimal("0.00")
        return self.amount_received or Decimal("0.00")

    @property
    def pending_amount(self) -> Decimal:
        if not self.has_pending:
            return Decimal("0.00")
        deal = self.final_deal_amount or Decimal("0.00")
        rec = self.amount_received or Decimal("0.00")
        diff = deal - rec
        return diff if diff > Decimal("0.00") else Decimal("0.00")

    @property
    def payment_status(self) -> str:
        return "Payment Pending" if self.pending_amount > Decimal("0.00") else "Paid"


class BillItem(Base):
    """Line item purchased on a customer bill (either from dropdown or custom textbox)."""
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey("customer_bills.id", ondelete="CASCADE"), nullable=False, index=True)
    entry_type = Column(String(20), nullable=False, default="DROPDOWN")  # 'DROPDOWN' or 'CUSTOM'
    category_id = Column(Integer, ForeignKey("item_categories.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(Integer, ForeignKey("item_products.id", ondelete="SET NULL"), nullable=True)
    pack_size_id = Column(Integer, ForeignKey("item_pack_sizes.id", ondelete="SET NULL"), nullable=True)

    # Snapshots ensure customer bill history remains intact even if dropdown items change
    category_name = Column(String(150), nullable=True)
    product_name = Column(String(250), nullable=False)
    pack_size = Column(String(100), nullable=True)
    quantity = Column(Numeric(10, 2), default=Decimal("1.00"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    bill = relationship("CustomerBill", back_populates="items")

    @property
    def display_label(self) -> str:
        qty_str = f"{int(self.quantity)}" if self.quantity == int(self.quantity) else f"{self.quantity:.2f}"
        if self.pack_size:
            return f"{self.product_name} – {self.pack_size} (Qty: {qty_str})"
        return f"{self.product_name} (Qty: {qty_str})"


class BillPayment(Base):
    """Payment log entry for partial or full settlements on a customer bill."""
    __tablename__ = "bill_payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey("customer_bills.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    payment_date = Column(Date, default=date.today, nullable=False, index=True)
    payment_method = Column(String(30), default="Cash", nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    bill = relationship("CustomerBill", back_populates="payments")
    customer = relationship("Customer", back_populates="payments")


class AuditLog(Base):
    """Security & change audit trail."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username = Column(String(50), nullable=False, default="system")
    action = Column(String(100), nullable=False, index=True)
    record_type = Column(String(50), nullable=False)
    record_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class BackupLog(Base):
    """Tracks manual/automated database backups."""
    __tablename__ = "backup_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, default=0)
    backup_type = Column(String(30), default="MANUAL")
    status = Column(String(20), default="SUCCESS")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
