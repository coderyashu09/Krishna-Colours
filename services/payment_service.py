"""
Payment Management Service.
Handles multiple payments per bill, partial payments, payment method tracking,
overpayment prevention, payment reversals, and customer statements.
All financial logic strictly uses Decimal arithmetic.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import Session

from database.models import Payment, Bill, Customer
from services.audit_service import log_activity


class OverpaymentError(Exception):
    """Raised when payment exceeds bill outstanding amount without authorization."""
    pass


def generate_payment_number(db: Session, prefix: str = "PAY-") -> str:
    """Generate sequential payment receipt number."""
    count = db.execute(select(func.count(Payment.id))).scalar() or 0
    today_str = datetime.utcnow().strftime("%Y%m%d")
    return f"{prefix}{today_str}-{count + 1:04d}"


def record_payment(
    db: Session,
    customer_id: int,
    amount: Decimal,
    bill_id: Optional[int] = None,
    payment_date: Optional[date] = None,
    payment_method: str = "CASH",
    transaction_reference: Optional[str] = None,
    notes: Optional[str] = None,
    allow_overpayment: bool = False,
    user_id: Optional[int] = None,
    username: str = "system",
) -> Payment:
    """
    Record payment against a specific bill or customer account.
    Updates bill amount_received, outstanding_amount, and payment_status.
    Prevents overpayment unless allow_overpayment is True.
    """
    pay_amt = Decimal(str(amount))
    if pay_amt <= Decimal("0.00"):
        raise ValueError("Payment amount must be greater than zero.")

    customer = db.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if not customer:
        raise ValueError(f"Customer with ID {customer_id} does not exist.")

    bill: Optional[Bill] = None
    if bill_id:
        bill = db.execute(select(Bill).where(Bill.id == bill_id)).scalar_one_or_none()
        if not bill:
            raise ValueError(f"Bill with ID {bill_id} does not exist.")
        if bill.customer_id != customer_id:
            raise ValueError("Bill does not belong to the selected customer.")
        if bill.bill_status == "CANCELLED":
            raise ValueError(f"Cannot accept payment against cancelled bill {bill.bill_number}.")

        if not allow_overpayment and pay_amt > bill.outstanding_amount:
            raise OverpaymentError(
                f"Payment amount (₹{pay_amt}) exceeds outstanding balance (₹{bill.outstanding_amount}) for Bill {bill.bill_number}."
            )

    pay_no = generate_payment_number(db)
    payment = Payment(
        payment_number=pay_no,
        customer_id=customer_id,
        bill_id=bill.id if bill else None,
        amount=pay_amt,
        payment_date=payment_date or date.today(),
        payment_method=payment_method,
        transaction_reference=transaction_reference,
        notes=notes,
        created_by_user_id=user_id,
        is_reversal=False,
    )
    db.add(payment)

    # If linked to a bill, update bill status and balances
    if bill:
        bill.amount_received = bill.amount_received + pay_amt
        bill.outstanding_amount = bill.grand_total - bill.amount_received
        if bill.outstanding_amount < Decimal("0.00"):
            bill.outstanding_amount = Decimal("0.00")

        if bill.outstanding_amount == Decimal("0.00"):
            bill.payment_status = "PAID"
        elif bill.amount_received > Decimal("0.00"):
            bill.payment_status = "PARTIALLY_PAID"
        else:
            bill.payment_status = "PENDING"
        bill.updated_at = datetime.utcnow()

    db.flush()

    ref_bill_text = f" against Bill {bill.bill_number}" if bill else " on account"
    log_activity(
        db=db,
        action="PAYMENT_RECEIVE",
        record_type="PAYMENT",
        record_id=str(payment.id),
        details=f"Received ₹{pay_amt} via {payment_method}{ref_bill_text} from '{customer.name}'. Receipt: {payment.payment_number}",
        user_id=user_id,
        username=username,
    )
    return payment


def reverse_payment(
    db: Session,
    payment_id: int,
    reason: str,
    user_id: Optional[int] = None,
    username: str = "system",
) -> Payment:
    """
    Reverse / refund a payment transaction.
    Adjusts the associated bill outstanding amount accordingly.
    """
    payment = db.execute(select(Payment).where(Payment.id == payment_id)).scalar_one_or_none()
    if not payment:
        raise ValueError(f"Payment with ID {payment_id} not found.")

    if payment.is_reversal:
        raise ValueError(f"Payment {payment.payment_number} is already reversed.")

    payment.is_reversal = True
    payment.notes = f"{payment.notes or ''} [REVERSED: {reason}]"

    # Adjust associated bill if present
    if payment.bill_id:
        bill = db.execute(select(Bill).where(Bill.id == payment.bill_id)).scalar_one_or_none()
        if bill and bill.bill_status != "CANCELLED":
            bill.amount_received = bill.amount_received - payment.amount
            if bill.amount_received < Decimal("0.00"):
                bill.amount_received = Decimal("0.00")
            bill.outstanding_amount = bill.grand_total - bill.amount_received

            if bill.outstanding_amount == Decimal("0.00"):
                bill.payment_status = "PAID"
            elif bill.amount_received > Decimal("0.00"):
                bill.payment_status = "PARTIALLY_PAID"
            else:
                bill.payment_status = "PENDING"
            bill.updated_at = datetime.utcnow()

    db.flush()

    log_activity(
        db=db,
        action="PAYMENT_REVERSE",
        record_type="PAYMENT",
        record_id=str(payment.id),
        details=f"Reversed payment {payment.payment_number} (₹{payment.amount}). Reason: {reason}",
        user_id=user_id,
        username=username,
    )
    return payment


def get_payments(
    db: Session,
    customer_id: Optional[int] = None,
    bill_id: Optional[int] = None,
    payment_method: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    include_reversals: bool = False,
) -> List[Payment]:
    """Retrieve payments with filtering."""
    query = select(Payment).join(Customer, Customer.id == Payment.customer_id)

    if not include_reversals:
        query = query.where(Payment.is_reversal == False)
    if customer_id:
        query = query.where(Payment.customer_id == customer_id)
    if bill_id:
        query = query.where(Payment.bill_id == bill_id)
    if payment_method and payment_method != "All":
        query = query.where(Payment.payment_method == payment_method)
    if start_date:
        query = query.where(Payment.payment_date >= start_date)
    if end_date:
        query = query.where(Payment.payment_date <= end_date)

    query = query.order_by(Payment.payment_date.desc(), Payment.id.desc())
    return list(db.execute(query).scalars().all())


def get_customer_statement(db: Session, customer_id: int) -> Dict[str, Any]:
    """Generate consolidated chronological ledger statement for a customer."""
    customer = db.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if not customer:
        raise ValueError(f"Customer {customer_id} not found.")

    bills = list(
        db.execute(
            select(Bill)
            .where(and_(Bill.customer_id == customer_id, Bill.bill_status != "CANCELLED"))
            .order_by(Bill.bill_date.asc(), Bill.id.asc())
        ).scalars().all()
    )

    payments = list(
        db.execute(
            select(Payment)
            .where(and_(Payment.customer_id == customer_id, Payment.is_reversal == False))
            .order_by(Payment.payment_date.asc(), Payment.id.asc())
        ).scalars().all()
    )

    # Merge entries into chronological ledger
    ledger_entries = []
    for b in bills:
        ledger_entries.append({
            "date": b.bill_date,
            "type": "INVOICE",
            "ref_number": b.bill_number,
            "description": f"Bill #{b.bill_number} ({len(b.items)} items)",
            "debit": b.grand_total,
            "credit": Decimal("0.00"),
        })

    for p in payments:
        bill_ref = f" (Bill #{p.bill.bill_number})" if p.bill else ""
        ledger_entries.append({
            "date": p.payment_date,
            "type": "PAYMENT",
            "ref_number": p.payment_number,
            "description": f"Payment via {p.payment_method}{bill_ref}",
            "debit": Decimal("0.00"),
            "credit": p.amount,
        })

    # Sort by date
    ledger_entries.sort(key=lambda x: x["date"])

    running_balance = Decimal("0.00")
    for entry in ledger_entries:
        running_balance += (entry["debit"] - entry["credit"])
        entry["balance"] = running_balance

    total_billed = sum((b.grand_total for b in bills), Decimal("0.00"))
    total_paid = sum((p.amount for p in payments), Decimal("0.00"))
    net_outstanding = total_billed - total_paid

    return {
        "customer": customer,
        "total_billed": total_billed,
        "total_paid": total_paid,
        "net_outstanding": net_outstanding,
        "ledger": ledger_entries,
    }
