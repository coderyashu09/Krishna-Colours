"""
Billing Service for Krishna Colour - Asian Paints.
Supports manual & automatic bill numbering, duplicate prevention, multi-item calculation,
inventory deduction upon finalization, and exact-once inventory reversal upon cancellation.
All financial arithmetic strictly uses Python Decimal.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import uuid4
from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import Session

from database.models import Bill, BillItem, Product, Customer, Payment, StockTransaction
from services.audit_service import log_activity
from services.inventory_service import record_stock_out, cancel_stock_transaction, NegativeStockError


class DuplicateBillNumberError(Exception):
    """Raised when bill number already exists in the system."""
    pass


class InvalidBillOperationError(Exception):
    """Raised when an illegal bill state transition is attempted."""
    pass


def generate_bill_number(db: Session, prefix: str = "KC-") -> str:
    """Generate next available automatic bill number (e.g. KC-2026-0001)."""
    year = datetime.utcnow().year
    year_prefix = f"{prefix}{year}-"
    # Find max existing sequence for current year
    highest_bill = (
        db.execute(
            select(Bill.bill_number)
            .where(Bill.bill_number.like(f"{year_prefix}%"))
            .order_by(Bill.id.desc())
        )
        .scalars()
        .first()
    )
    if highest_bill:
        try:
            seq_part = highest_bill.split("-")[-1]
            next_seq = int(seq_part) + 1
        except Exception:
            next_seq = 1
    else:
        # Check overall count
        total_bills = db.execute(select(func.count(Bill.id))).scalar() or 0
        next_seq = total_bills + 1
    return f"{year_prefix}{next_seq:04d}"


def calculate_bill_totals(
    items_data: List[Dict[str, Any]],
    discount: Decimal = Decimal("0.00"),
    tax_rate: Decimal = Decimal("0.00"),
) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    Calculate subtotal, discount, tax_amount, and grand_total with Decimal precision.
    Returns: (subtotal, discount, tax_amount, grand_total)
    """
    subtotal = Decimal("0.00")
    for item in items_data:
        qty = Decimal(str(item["quantity"]))
        unit_p = Decimal(str(item["unit_price"]))
        item_disc = Decimal(str(item.get("discount_amount", 0.00)))
        line_total = (qty * unit_p) - item_disc
        if line_total < Decimal("0.00"):
            line_total = Decimal("0.00")
        subtotal += line_total

    disc = Decimal(str(discount))
    if disc < Decimal("0.00"):
        disc = Decimal("0.00")
    if disc > subtotal:
        disc = subtotal

    taxable_amount = subtotal - disc
    t_rate = Decimal(str(tax_rate))
    tax_amount = (taxable_amount * t_rate / Decimal("100.00")).quantize(Decimal("0.01"))
    grand_total = (taxable_amount + tax_amount).quantize(Decimal("0.01"))
    return subtotal, disc, tax_amount, grand_total


def create_bill(
    db: Session,
    customer_id: int,
    items_data: List[Dict[str, Any]],
    bill_number: Optional[str] = None,
    bill_date: Optional[date] = None,
    discount: Decimal = Decimal("0.00"),
    tax_rate: Decimal = Decimal("0.00"),
    initial_payment_amount: Decimal = Decimal("0.00"),
    payment_method: str = "CASH",
    payment_reference: Optional[str] = None,
    notes: Optional[str] = None,
    bill_status: str = "FINALIZED",  # 'FINALIZED' or 'DRAFT'
    allow_negative_stock: bool = False,
    user_id: Optional[int] = None,
    username: str = "system",
) -> Bill:
    """
    Create a bill with multi-item line totals.
    If bill_number is provided (manual), checks uniqueness. Otherwise auto-generates.
    If bill_status == 'FINALIZED', decrements product stock and records StockTransactions.
    If initial_payment_amount > 0, records the payment and adjusts outstanding amount.
    """
    if not items_data:
        raise ValueError("A bill must contain at least one product item.")

    # Validate Customer
    customer = db.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if not customer:
        raise ValueError(f"Customer with ID {customer_id} does not exist.")

    # Bill Number Handling
    if bill_number:
        clean_bill_no = str(bill_number).strip()
    else:
        clean_bill_no = generate_bill_number(db)

    # Prevent Duplicate Bill Number
    existing = db.execute(select(Bill).where(Bill.bill_number == clean_bill_no)).scalar_one_or_none()
    if existing:
        raise DuplicateBillNumberError(f"Bill number '{clean_bill_no}' already exists in the system.")

    # Calculate Totals
    subtotal, disc, tax_amt, grand_total = calculate_bill_totals(items_data, discount, tax_rate)

    init_payment = Decimal(str(initial_payment_amount))
    if init_payment < Decimal("0.00"):
        init_payment = Decimal("0.00")
    if init_payment > grand_total:
        init_payment = grand_total

    outstanding = grand_total - init_payment

    if outstanding == Decimal("0.00"):
        pay_status = "PAID"
    elif init_payment > Decimal("0.00"):
        pay_status = "PARTIALLY_PAID"
    else:
        pay_status = "PENDING"

    bill = Bill(
        bill_number=clean_bill_no,
        customer_id=customer_id,
        bill_date=bill_date or date.today(),
        subtotal=subtotal,
        discount=disc,
        tax_rate=Decimal(str(tax_rate)),
        tax_amount=tax_amt,
        grand_total=grand_total,
        amount_received=init_payment,
        outstanding_amount=outstanding,
        payment_status=pay_status,
        bill_status=bill_status,
        notes=notes,
        created_by_user_id=user_id,
    )
    db.add(bill)
    db.flush()

    # Create Bill Items
    for idx, item in enumerate(items_data, start=1):
        prod_id = item["product_id"]
        product = db.execute(select(Product).where(Product.id == prod_id)).scalar_one_or_none()
        if not product:
            raise ValueError(f"Product ID {prod_id} not found.")

        qty = Decimal(str(item["quantity"]))
        unit_p = Decimal(str(item["unit_price"]))
        item_disc = Decimal(str(item.get("discount_amount", "0.00")))
        line_tot = (qty * unit_p) - item_disc
        if line_tot < Decimal("0.00"):
            line_tot = Decimal("0.00")

        b_item = BillItem(
            bill_id=bill.id,
            product_id=product.id,
            product_name=product.name,
            quantity=qty,
            unit_price=unit_p,
            discount_amount=item_disc,
            line_total=line_tot,
        )
        db.add(b_item)

        # If FINALIZED, deduct stock transactionally
        if bill_status == "FINALIZED":
            if not allow_negative_stock and (product.current_stock - qty) < Decimal("0.00"):
                raise NegativeStockError(
                    f"Insufficient stock for '{product.name}'. Current: {product.current_stock} {product.unit}, Required: {qty} {product.unit}."
                )

            # Record stock movement with collision-free unique transaction code
            stx_code = f"STX-SALE-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{bill.id or 0}-{idx:03d}-{uuid4().hex[:4].upper()}"
            tx = StockTransaction(
                transaction_code=stx_code,
                transaction_type="BILL_SALE",
                product_id=product.id,
                quantity=qty,
                unit_price=unit_p,
                reference_type="BILL",
                reference_id=bill.bill_number,
                party_name=customer.name,
                notes=f"Sale on Bill {bill.bill_number}",
                created_by_user_id=user_id,
                is_cancelled=False,
                created_at=datetime.utcnow()
            )
            db.add(tx)
            product.current_stock = product.current_stock - qty
            product.updated_at = datetime.utcnow()

    # Record Initial Payment if provided
    if init_payment > Decimal("0.00"):
        pay_no = f"PAY-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:4].upper()}"
        payment = Payment(
            payment_number=pay_no,
            customer_id=customer_id,
            bill_id=bill.id,
            amount=init_payment,
            payment_date=bill.bill_date,
            payment_method=payment_method,
            transaction_reference=payment_reference,
            notes=f"Initial payment on Bill {bill.bill_number}",
            created_by_user_id=user_id,
            is_reversal=False,
        )
        db.add(payment)

    db.flush()

    log_activity(
        db=db,
        action="BILL_GENERATE",
        record_type="BILL",
        record_id=str(bill.id),
        details=f"Generated Bill {bill.bill_number} for customer '{customer.name}'. Total: ₹{grand_total}, Status: {bill_status}, Payment: {pay_status}",
        user_id=user_id,
        username=username,
    )
    return bill


def cancel_bill(
    db: Session,
    bill_id: int,
    reason: str,
    user_id: Optional[int] = None,
    username: str = "system",
) -> Bill:
    """
    Safely cancel a bill.
    Reverses all inventory deductions exactly once.
    Marks bill as CANCELLED.
    Records audit entry.
    """
    bill = db.execute(select(Bill).where(Bill.id == bill_id)).scalar_one_or_none()
    if not bill:
        raise ValueError(f"Bill ID {bill_id} not found.")

    if bill.bill_status == "CANCELLED":
        raise InvalidBillOperationError(f"Bill {bill.bill_number} is already cancelled.")

    was_finalized = (bill.bill_status == "FINALIZED")

    # If finalized, reverse stock deductions
    if was_finalized:
        for idx, item in enumerate(bill.items, start=1):
            product = db.execute(select(Product).where(Product.id == item.product_id)).scalar_one()
            product.current_stock = product.current_stock + item.quantity
            product.updated_at = datetime.utcnow()

            stx_code = f"STX-REV-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{bill.id}-{idx:03d}-{uuid4().hex[:4].upper()}"
            tx = StockTransaction(
                transaction_code=stx_code,
                transaction_type="BILL_CANCEL",
                product_id=product.id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                reference_type="BILL",
                reference_id=bill.bill_number,
                party_name=bill.customer.name,
                notes=f"Stock reversal for cancelled Bill {bill.bill_number}. Reason: {reason}",
                created_by_user_id=user_id,
                is_cancelled=False,
                created_at=datetime.utcnow()
            )
            db.add(tx)

    bill.bill_status = "CANCELLED"
    bill.notes = f"{bill.notes or ''} [CANCELLED on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}: {reason}]"
    bill.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db=db,
        action="BILL_CANCEL",
        record_type="BILL",
        record_id=str(bill.id),
        details=f"Cancelled Bill {bill.bill_number}. Stock restored. Reason: {reason}",
        user_id=user_id,
        username=username,
    )
    return bill


def get_bills(
    db: Session,
    customer_id: Optional[int] = None,
    payment_status: Optional[str] = None,
    bill_status: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Bill]:
    """Search and filter bills list."""
    query = select(Bill).join(Customer, Customer.id == Bill.customer_id)

    if customer_id:
        query = query.where(Bill.customer_id == customer_id)
    if payment_status and payment_status != "All":
        query = query.where(Bill.payment_status == payment_status)
    if bill_status and bill_status != "All":
        query = query.where(Bill.bill_status == bill_status)
    if start_date:
        query = query.where(Bill.bill_date >= start_date)
    if end_date:
        query = query.where(Bill.bill_date <= end_date)

    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Bill.bill_number.ilike(term),
                Customer.name.ilike(term),
                Customer.mobile.ilike(term),
            )
        )

    query = query.order_by(Bill.bill_date.desc(), Bill.id.desc())
    return list(db.execute(query).scalars().all())
