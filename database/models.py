"""
SQLAlchemy ORM models for Krishna Colour - Asian Paints.
Full relational design with numeric precision for all monetary values.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Boolean,
    DateTime, Date, ForeignKey, Index, func
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False, default="staff")  # 'admin' or 'staff'
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at,
        }


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False, index=True)
    contact_person = Column(String(100), nullable=True)
    mobile = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)
    brand = Column(String(100), default="Asian Paints", nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    subcategory = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    unit = Column(String(20), default="Litre", nullable=False)
    purchase_price = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    selling_price = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    current_stock = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    min_stock_level = Column(Numeric(12, 2), default=Decimal("5.00"), nullable=False)
    status = Column(String(20), default="active", nullable=False)  # 'active', 'discontinued'
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    stock_transactions = relationship("StockTransaction", back_populates="product")
    bill_items = relationship("BillItem", back_populates="product")


class StockTransaction(Base):
    __tablename__ = "stock_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_code = Column(String(50), unique=True, nullable=False, index=True)
    transaction_type = Column(String(30), nullable=False, index=True)
    # Types: 'STOCK_IN', 'STOCK_OUT', 'BILL_SALE', 'SHOP_ISSUE', 'SHOP_RETURN', 'ADJUSTMENT', 'BILL_CANCEL'
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Numeric(12, 2), nullable=False)  # positive number
    unit_price = Column(Numeric(12, 2), default=Decimal("0.00"))
    reference_type = Column(String(30), nullable=True)  # 'SUPPLIER_INVOICE', 'BILL', 'SHOP_ISSUE', 'SHOP_RETURN', 'MANUAL'
    reference_id = Column(String(100), nullable=True, index=True)
    party_name = Column(String(150), nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_cancelled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    product = relationship("Product", back_populates="stock_transactions")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    mobile = Column(String(20), nullable=False, index=True)
    alternate_mobile = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(20), default="active", nullable=False)  # 'active', 'inactive'
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bills = relationship("Bill", back_populates="customer")
    payments = relationship("Payment", back_populates="customer")


class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_number = Column(String(50), unique=True, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    bill_date = Column(Date, default=date.today, nullable=False, index=True)
    subtotal = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    discount = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    tax_rate = Column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    tax_amount = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    grand_total = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    amount_received = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    outstanding_amount = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    payment_status = Column(String(20), default="PENDING", nullable=False, index=True)  # 'PENDING', 'PARTIALLY_PAID', 'PAID'
    bill_status = Column(String(20), default="FINALIZED", nullable=False, index=True)  # 'DRAFT', 'FINALIZED', 'CANCELLED'
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="bills")
    items = relationship("BillItem", back_populates="bill", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="bill")


class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    discount_amount = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    line_total = Column(Numeric(12, 2), nullable=False)

    bill = relationship("Bill", back_populates="items")
    product = relationship("Product", back_populates="bill_items")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    payment_number = Column(String(50), unique=True, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    payment_date = Column(Date, default=date.today, nullable=False, index=True)
    payment_method = Column(String(30), default="CASH", nullable=False)  # 'CASH', 'UPI', 'BANK_TRANSFER', 'CHEQUE', 'OTHER'
    transaction_reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_reversal = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    customer = relationship("Customer", back_populates="payments")
    bill = relationship("Bill", back_populates="payments")


class OtherShop(Base):
    __tablename__ = "other_shops"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shop_code = Column(String(50), unique=True, nullable=False, index=True)
    shop_name = Column(String(150), nullable=False, index=True)
    owner_name = Column(String(100), nullable=True)
    mobile = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(20), default="active", nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    issues = relationship("ShopIssue", back_populates="other_shop")
    returns = relationship("ShopReturn", back_populates="other_shop")


class ShopIssue(Base):
    __tablename__ = "shop_issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_number = Column(String(50), unique=True, nullable=False, index=True)
    shop_id = Column(Integer, ForeignKey("other_shops.id"), nullable=False, index=True)
    issue_date = Column(Date, default=date.today, nullable=False, index=True)
    reference_number = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(30), default="PENDING", nullable=False, index=True)
    # 'PENDING', 'PARTIALLY_RETURNED', 'COMPLETED'
    completed_at = Column(DateTime, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    other_shop = relationship("OtherShop", back_populates="issues")
    items = relationship("ShopIssueItem", back_populates="issue", cascade="all, delete-orphan")
    returns = relationship("ShopReturn", back_populates="issue")


class ShopIssueItem(Base):
    __tablename__ = "shop_issue_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_id = Column(Integer, ForeignKey("shop_issues.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity_issued = Column(Numeric(12, 2), nullable=False)
    quantity_returned = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    unit_price = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    status = Column(String(30), default="PENDING", nullable=False)
    # 'PENDING', 'PARTIALLY_RETURNED', 'COMPLETED'

    issue = relationship("ShopIssue", back_populates="items")
    product = relationship("Product")


class ShopReturn(Base):
    __tablename__ = "shop_returns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    return_number = Column(String(50), unique=True, nullable=False, index=True)
    shop_id = Column(Integer, ForeignKey("other_shops.id"), nullable=False, index=True)
    issue_id = Column(Integer, ForeignKey("shop_issues.id"), nullable=False, index=True)
    return_date = Column(Date, default=date.today, nullable=False, index=True)
    condition_notes = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    other_shop = relationship("OtherShop", back_populates="returns")
    issue = relationship("ShopIssue", back_populates="returns")
    items = relationship("ShopReturnItem", back_populates="return_obj", cascade="all, delete-orphan")


class ShopReturnItem(Base):
    __tablename__ = "shop_return_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    return_id = Column(Integer, ForeignKey("shop_returns.id"), nullable=False, index=True)
    issue_item_id = Column(Integer, ForeignKey("shop_issue_items.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity_returned = Column(Numeric(12, 2), nullable=False)
    condition_notes = Column(Text, nullable=True)

    return_obj = relationship("ShopReturn", back_populates="items")
    product = relationship("Product")
    issue_item = relationship("ShopIssueItem")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(100), default="system", nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)
    record_type = Column(String(50), nullable=False, index=True)
    record_id = Column(String(100), nullable=True, index=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class BusinessSetting(Base):
    __tablename__ = "business_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    setting_key = Column(String(100), unique=True, nullable=False, index=True)
    setting_value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BackupLog(Base):
    __tablename__ = "backup_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, default=0)
    backup_type = Column(String(20), default="MANUAL", nullable=False)
    status = Column(String(20), default="SUCCESS", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
