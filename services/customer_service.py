"""
Customer Management Service.
Manages customer profiles, code generation, ledger summaries, and soft deletion.
Supports unlimited bills per customer.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import Session

from database.models import Customer, Bill, Payment, BillItem
from services.audit_service import log_activity


def generate_customer_code(db: Session, prefix: str = "KC-CUST-") -> str:
    """Generate sequential customer code."""
    count = db.execute(select(func.count(Customer.id))).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def create_customer(
    db: Session,
    name: str,
    mobile: str,
    alternate_mobile: Optional[str] = None,
    address: Optional[str] = None,
    city: Optional[str] = None,
    notes: Optional[str] = None,
    customer_code: Optional[str] = None,
    user_id: Optional[int] = None,
    username: str = "system",
) -> Customer:
    """Create a new customer record."""
    clean_mobile = mobile.strip()
    if not customer_code:
        customer_code = generate_customer_code(db)

    # Check for existing customer code
    existing_code = db.execute(select(Customer).where(Customer.customer_code == customer_code)).scalar_one_or_none()
    if existing_code:
        raise ValueError(f"Customer code '{customer_code}' already exists.")

    customer = Customer(
        customer_code=customer_code.strip(),
        name=name.strip(),
        mobile=clean_mobile,
        alternate_mobile=alternate_mobile.strip() if alternate_mobile else None,
        address=address.strip() if address else None,
        city=city.strip() if city else None,
        notes=notes.strip() if notes else None,
        status="active",
        is_deleted=False,
    )
    db.add(customer)
    db.flush()

    log_activity(
        db=db,
        action="CREATE_CUSTOMER",
        record_type="CUSTOMER",
        record_id=str(customer.id),
        details=f"Created customer '{customer.name}' ({customer.customer_code}), Mobile: {customer.mobile}",
        user_id=user_id,
        username=username,
    )
    return customer


def update_customer(
    db: Session,
    customer_id: int,
    name: Optional[str] = None,
    mobile: Optional[str] = None,
    alternate_mobile: Optional[str] = None,
    address: Optional[str] = None,
    city: Optional[str] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    username: str = "system",
) -> Customer:
    """Update customer details."""
    customer = db.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if not customer:
        raise ValueError(f"Customer with ID {customer_id} not found.")

    changes = []
    if name is not None and name != customer.name:
        changes.append(f"Name: {customer.name} -> {name}")
        customer.name = name.strip()
    if mobile is not None and mobile != customer.mobile:
        changes.append(f"Mobile: {customer.mobile} -> {mobile}")
        customer.mobile = mobile.strip()
    if alternate_mobile is not None:
        customer.alternate_mobile = alternate_mobile.strip() if alternate_mobile else None
    if address is not None:
        customer.address = address.strip() if address else None
    if city is not None:
        customer.city = city.strip() if city else None
    if notes is not None:
        customer.notes = notes.strip() if notes else None
    if status is not None:
        customer.status = status

    customer.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db=db,
        action="UPDATE_CUSTOMER",
        record_type="CUSTOMER",
        record_id=str(customer.id),
        details=f"Updated customer '{customer.name}': " + ("; ".join(changes) if changes else "profile updated"),
        user_id=user_id,
        username=username,
    )
    return customer


def delete_customer(
    db: Session,
    customer_id: int,
    user_id: Optional[int] = None,
    username: str = "system",
) -> bool:
    """
    Safely delete customer. If the customer has financial history (bills, payments),
    performs a soft-delete to preserve all historical accounting records.
    """
    customer = db.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if not customer:
        raise ValueError(f"Customer with ID {customer_id} not found.")

    has_bills = db.execute(select(func.count(Bill.id)).where(Bill.customer_id == customer_id)).scalar() or 0
    has_payments = db.execute(select(func.count(Payment.id)).where(Payment.customer_id == customer_id)).scalar() or 0

    if has_bills > 0 or has_payments > 0:
        # Soft delete
        customer.is_deleted = True
        customer.status = "inactive"
        customer.updated_at = datetime.utcnow()
        db.flush()
        msg = "Soft-deleted (deactivated) to protect financial ledger history"
    else:
        db.delete(customer)
        db.flush()
        msg = "Hard-deleted (no financial records attached)"

    log_activity(
        db=db,
        action="DELETE_CUSTOMER",
        record_type="CUSTOMER",
        record_id=str(customer_id),
        details=f"Customer '{customer.name}' ({customer.customer_code}): {msg}",
        user_id=user_id,
        username=username,
    )
    return True


def get_customers(
    db: Session,
    search: Optional[str] = None,
    status: Optional[str] = None,
    include_deleted: bool = False,
) -> List[Customer]:
    """Search and filter customer directory."""
    query = select(Customer)
    if not include_deleted:
        query = query.where(Customer.is_deleted == False)

    if status and status != "All":
        query = query.where(Customer.status == status)

    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Customer.name.ilike(term),
                Customer.mobile.ilike(term),
                Customer.customer_code.ilike(term),
                Customer.city.ilike(term),
            )
        )

    query = query.order_by(Customer.name.asc())
    return list(db.execute(query).scalars().all())


def get_customer_summary(db: Session, customer_id: int) -> Dict[str, Any]:
    """
    Compute complete financial summary and transaction history for a customer:
    Total purchase, Total paid, Outstanding balance, list of bills, list of payments.
    """
    customer = db.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if not customer:
        raise ValueError(f"Customer with ID {customer_id} not found.")

    # All non-cancelled bills
    bills_query = (
        select(Bill)
        .where(and_(Bill.customer_id == customer_id, Bill.bill_status != "CANCELLED"))
        .order_by(Bill.bill_date.desc(), Bill.id.desc())
    )
    bills = list(db.execute(bills_query).scalars().all())

    # All payments
    payments_query = (
        select(Payment)
        .where(and_(Payment.customer_id == customer_id, Payment.is_reversal == False))
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
    )
    payments = list(db.execute(payments_query).scalars().all())

    total_purchase = sum((b.grand_total for b in bills), Decimal("0.00"))
    total_paid = sum((p.amount for p in payments), Decimal("0.00"))
    outstanding_balance = sum((b.outstanding_amount for b in bills), Decimal("0.00"))

    # Product purchase breakdown
    product_history_query = (
        select(
            BillItem.product_name,
            func.sum(BillItem.quantity).label("total_qty"),
            func.sum(BillItem.line_total).label("total_spent")
        )
        .join(Bill, Bill.id == BillItem.bill_id)
        .where(and_(Bill.customer_id == customer_id, Bill.bill_status != "CANCELLED"))
        .group_by(BillItem.product_name)
        .order_by(func.sum(BillItem.line_total).desc())
    )
    products_bought = [
        {"product_name": r[0], "quantity": r[1], "total_spent": r[2]}
        for r in db.execute(product_history_query).all()
    ]

    return {
        "customer": customer,
        "total_purchase": total_purchase,
        "total_paid": total_paid,
        "outstanding_balance": outstanding_balance,
        "bills": bills,
        "payments": payments,
        "products_bought": products_bought,
        "pending_bills_count": sum(1 for b in bills if b.outstanding_amount > Decimal("0.00")),
    }
