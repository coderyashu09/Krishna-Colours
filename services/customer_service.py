"""
Customer, Multi-Bill, and Final-Deal Payment Management Service
for Krishna Colour – Asian Paints Customer Management System.

Key Business Rules:
- Auto-generates unique customer codes: KC-000001, KC-000002, ...
- Supports multiple manually entered bill numbers per customer (1 to 5+ digits).
- Prevents accidental duplicate bill numbers for the same customer.
- Only two monetary fields:
  1. Final Deal Amount
  2. Amount Received
- Default (has_pending=False): there is NO pending amount; Amount Received is the final closed amount (Paid).
- Optional (has_pending=True): Pending Amount = Final Deal Amount - Amount Received.
  If Pending Amount == 0, automatically marked Paid / Done.
- Year Amount & Month Amount sum Amount Received for closed deals and Final Deal Amount for active pending-tracked deals.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy import select, or_, func, extract, case
from sqlalchemy.orm import Session, selectinload

from database.models import (
    Customer, CustomerBill, BillItem, BillPayment,
    ItemCategory, ItemProduct, ItemPackSize,
)
from utils.validators import validate_mobile
from services.audit_service import log_activity


class DuplicateCustomerError(Exception):
    """Raised when registering a duplicate customer mobile number."""
    pass


class DuplicateBillNumberError(Exception):
    """Raised when adding a duplicate bill number to the same customer."""
    pass


class InvalidAmountError(Exception):
    """Raised when monetary validation fails (e.g. negative or received > final deal)."""
    pass


def generate_customer_code(db: Session) -> str:
    """Generate sequential Customer ID: KC-000001, KC-000002, ..."""
    codes = db.execute(select(Customer.customer_code)).scalars().all()
    max_num = 0
    for code in codes:
        if code and code.startswith("KC-"):
            part = code.replace("KC-", "").strip()
            if part.isdigit():
                max_num = max(max_num, int(part))
    return f"KC-{max_num + 1:06d}"


def _validate_bill_amounts(
    final_deal_amount: Decimal,
    amount_received: Decimal,
    has_pending: bool = False,
) -> tuple[Decimal, Decimal]:
    """Validate Final Deal Amount and Amount Received strictly using Decimal."""
    deal = Decimal(str(final_deal_amount)).quantize(Decimal("0.01"))
    if deal < Decimal("0.00"):
        raise InvalidAmountError("Final Deal Amount cannot be negative.")

    rec = Decimal(str(amount_received)).quantize(Decimal("0.01"))
    if rec < Decimal("0.00"):
        raise InvalidAmountError("Amount Received cannot be negative.")

    if has_pending and rec > deal:
        raise InvalidAmountError(
            f"Amount Received (₹{rec:,.2f}) cannot exceed Final Deal Amount (₹{deal:,.2f}) when Pending Amount is enabled."
        )
    return deal, rec


def _attach_bill_items(db: Session, bill: CustomerBill, items_data: List[Dict[str, Any]]):
    """Persist dropdown or custom items on a CustomerBill with snapshot labels."""
    for item in items_data:
        entry_type = str(item.get("entry_type", "DROPDOWN")).upper()
        qty = Decimal(str(item.get("quantity", "1.00")))
        if qty <= Decimal("0.00"):
            raise ValueError("Item quantity must be greater than zero.")

        if entry_type == "CUSTOM":
            prod_name = str(item.get("product_name", "")).strip()
            if not prod_name:
                raise ValueError("Custom item name cannot be empty.")
            pack_lbl = str(item.get("pack_size", "") or "").strip() or None
            db.add(
                BillItem(
                    bill_id=bill.id,
                    entry_type="CUSTOM",
                    category_name="Custom Item",
                    product_name=prod_name,
                    pack_size=pack_lbl,
                    quantity=qty,
                )
            )
        else:
            cat_id = item.get("category_id")
            prod_id = item.get("product_id")
            ps_id = item.get("pack_size_id")
            cat_name = item.get("category_name")
            prod_name = item.get("product_name")
            pack_lbl = item.get("pack_size")

            if cat_id and not cat_name:
                cat_obj = db.get(ItemCategory, cat_id)
                cat_name = cat_obj.name if cat_obj else None
            if prod_id and not prod_name:
                prod_obj = db.get(ItemProduct, prod_id)
                prod_name = prod_obj.name if prod_obj else None
            if ps_id and not pack_lbl:
                ps_obj = db.get(ItemPackSize, ps_id)
                pack_lbl = ps_obj.size_label if ps_obj else None

            if not prod_name:
                raise ValueError("Please select a product for each dropdown item.")

            db.add(
                BillItem(
                    bill_id=bill.id,
                    entry_type="DROPDOWN",
                    category_id=cat_id,
                    product_id=prod_id,
                    pack_size_id=ps_id,
                    category_name=cat_name,
                    product_name=prod_name,
                    pack_size=pack_lbl,
                    quantity=qty,
                )
            )


def create_customer(
    db: Session,
    name: str,
    mobile: str,
    address: str = "",
    bills_data: Optional[List[Dict[str, Any]]] = None,
    notes: Optional[str] = None,
    username: str = "admin",
) -> Customer:
    """
    Create a new customer with unique KC-XXXXXX ID and optionally one or more initial bills.
    Prevents accidental duplicate customers (by mobile number) and duplicate bill numbers.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Customer Name is required.")

    ok_mob, clean_mob = validate_mobile(mobile)
    if not ok_mob:
        raise ValueError(clean_mob)

    existing_cust = db.execute(
        select(Customer).where(Customer.mobile == clean_mob)
    ).scalar_one_or_none()
    if existing_cust:
        raise DuplicateCustomerError(
            f"A customer with mobile number {clean_mob} already exists: "
            f"{existing_cust.name} ({existing_cust.customer_code}). "
            "Open their profile to add more bills."
        )

    cust = Customer(
        customer_code=generate_customer_code(db),
        name=clean_name,
        mobile=clean_mob,
        address=(address or "").strip(),
        notes=(notes or "").strip() or None,
        is_active=True,
    )
    db.add(cust)
    db.flush()

    if bills_data:
        seen_bill_nos = set()
        for b in bills_data:
            b_no = str(b.get("bill_number", "")).strip()
            if not b_no:
                raise ValueError("Bill Number is required for every bill entry.")
            if b_no.lower() in seen_bill_nos:
                raise DuplicateBillNumberError(
                    f"Duplicate bill number '{b_no}' entered for customer {clean_name}."
                )
            seen_bill_nos.add(b_no.lower())

            add_bill_to_customer(
                db=db,
                customer_id=cust.id,
                bill_number=b_no,
                bill_date=b.get("bill_date") or date.today(),
                final_deal_amount=b.get("final_deal_amount", Decimal("0.00")),
                amount_received=b.get("amount_received", Decimal("0.00")),
                has_pending=bool(b.get("has_pending", False)),
                items_data=b.get("items", []),
                notes=b.get("notes"),
                payment_method=b.get("payment_method", "Cash"),
                username=username,
            )

    log_activity(
        db, "CREATE_CUSTOMER", "CUSTOMER", cust.customer_code,
        f"Registered customer {cust.name} ({cust.customer_code})", username=username
    )
    db.flush()
    return cust


def update_customer_details(
    db: Session,
    customer_id: int,
    name: str,
    mobile: str,
    address: str,
    notes: Optional[str] = None,
    is_active: bool = True,
    username: str = "admin",
) -> Customer:
    """Update customer profile information."""
    cust = db.get(Customer, customer_id)
    if not cust:
        raise ValueError("Customer not found.")

    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Customer Name is required.")

    ok_mob, clean_mob = validate_mobile(mobile)
    if not ok_mob:
        raise ValueError(clean_mob)

    dup = db.execute(
        select(Customer).where(Customer.mobile == clean_mob, Customer.id != customer_id)
    ).scalar_one_or_none()
    if dup:
        raise DuplicateCustomerError(
            f"Mobile number {clean_mob} belongs to {dup.name} ({dup.customer_code})."
        )

    cust.name = clean_name
    cust.mobile = clean_mob
    cust.address = (address or "").strip()
    cust.notes = (notes or "").strip() or None
    cust.is_active = bool(is_active)
    cust.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db, "UPDATE_CUSTOMER", "CUSTOMER", cust.customer_code,
        f"Updated customer {cust.name}", username=username
    )
    return cust


def add_bill_to_customer(
    db: Session,
    customer_id: int,
    bill_number: str,
    bill_date: date,
    final_deal_amount: Decimal,
    amount_received: Decimal,
    items_data: List[Dict[str, Any]],
    has_pending: bool = False,
    notes: Optional[str] = None,
    payment_method: str = "Cash",
    username: str = "admin",
) -> CustomerBill:
    """Add a new bill (with manual bill number, items, Final Deal Amount, and Amount Received) to a customer."""
    cust = db.get(Customer, customer_id)
    if not cust:
        raise ValueError("Customer not found.")

    clean_bill_no = (bill_number or "").strip()
    if not clean_bill_no:
        raise ValueError("Bill Number is required.")

    existing_bill = db.execute(
        select(CustomerBill).where(
            CustomerBill.customer_id == customer_id,
            func.lower(CustomerBill.bill_number) == clean_bill_no.lower(),
        )
    ).scalar_one_or_none()
    if existing_bill:
        raise DuplicateBillNumberError(
            f"Bill number '{clean_bill_no}' already exists for {cust.name} ({cust.customer_code})."
        )

    deal, rec = _validate_bill_amounts(final_deal_amount, amount_received, has_pending=has_pending)

    bill = CustomerBill(
        customer_id=customer_id,
        bill_number=clean_bill_no,
        bill_date=bill_date or date.today(),
        final_deal_amount=deal,
        amount_received=rec,
        has_pending=bool(has_pending and (deal - rec) > Decimal("0.00")),
        notes=(notes or "").strip() or None,
        created_by=username,
    )
    db.add(bill)
    db.flush()

    if items_data:
        _attach_bill_items(db, bill, items_data)

    if rec > Decimal("0.00"):
        db.add(
            BillPayment(
                bill_id=bill.id,
                customer_id=customer_id,
                amount=rec,
                payment_date=bill.bill_date,
                payment_method=payment_method or "Cash",
                notes=f"Initial amount received on Bill #{clean_bill_no}",
                created_by=username,
            )
        )

    db.flush()
    log_activity(
        db, "ADD_BILL", "CUSTOMER_BILL", clean_bill_no,
        f"Added Bill #{clean_bill_no} to {cust.name}: Final Deal ₹{deal:.2f}, Received ₹{rec:.2f}",
        username=username,
    )
    return bill


def update_bill(
    db: Session,
    bill_id: int,
    bill_number: str,
    bill_date: date,
    final_deal_amount: Decimal,
    amount_received: Decimal,
    has_pending: bool = False,
    items_data: Optional[List[Dict[str, Any]]] = None,
    notes: Optional[str] = None,
    username: str = "admin",
) -> CustomerBill:
    """
    Edit an existing bill's number, date, Final Deal Amount, Amount Received, optional pending flag, or items.
    """
    bill = db.get(CustomerBill, bill_id)
    if not bill:
        raise ValueError("Bill not found.")

    clean_bill_no = (bill_number or "").strip()
    if not clean_bill_no:
        raise ValueError("Bill Number is required.")

    dup = db.execute(
        select(CustomerBill).where(
            CustomerBill.customer_id == bill.customer_id,
            func.lower(CustomerBill.bill_number) == clean_bill_no.lower(),
            CustomerBill.id != bill_id,
        )
    ).scalar_one_or_none()
    if dup:
        raise DuplicateBillNumberError(
            f"Bill number '{clean_bill_no}' already exists for this customer."
        )

    deal, rec = _validate_bill_amounts(final_deal_amount, amount_received, has_pending=has_pending)

    old_rec = bill.amount_received or Decimal("0.00")
    bill.bill_number = clean_bill_no
    bill.bill_date = bill_date or bill.bill_date
    bill.final_deal_amount = deal
    bill.amount_received = rec
    bill.has_pending = bool(has_pending and (deal - rec) > Decimal("0.00"))
    bill.notes = (notes or "").strip() or None
    bill.updated_at = datetime.utcnow()

    if items_data is not None:
        # Replace bill items
        for old_item in list(bill.items):
            db.delete(old_item)
        db.flush()
        _attach_bill_items(db, bill, items_data)

    diff_rec = rec - old_rec
    if diff_rec != Decimal("0.00"):
        db.add(
            BillPayment(
                bill_id=bill.id,
                customer_id=bill.customer_id,
                amount=diff_rec,
                payment_date=date.today(),
                payment_method="Adjustment",
                notes=f"Admin amount adjustment on Bill #{clean_bill_no} (₹{old_rec:.2f} -> ₹{rec:.2f})",
                created_by=username,
            )
        )

    db.flush()
    log_activity(
        db, "UPDATE_BILL", "CUSTOMER_BILL", clean_bill_no,
        f"Updated Bill #{clean_bill_no}: Final Deal ₹{deal:.2f}, Received ₹{rec:.2f}",
        username=username,
    )
    return bill


def delete_bill(db: Session, bill_id: int, username: str = "admin") -> bool:
    """Remove a bill from a customer (cascades items & payments)."""
    bill = db.get(CustomerBill, bill_id)
    if not bill:
        raise ValueError("Bill not found.")
    b_no = bill.bill_number
    c_id = bill.customer_id
    db.delete(bill)
    db.flush()
    log_activity(db, "DELETE_BILL", "CUSTOMER_BILL", b_no, f"Removed Bill #{b_no} from customer ID {c_id}", username=username)
    return True


def record_bill_payment(
    db: Session,
    bill_id: int,
    payment_amount: Decimal,
    payment_date: Optional[date] = None,
    payment_method: str = "Cash",
    notes: Optional[str] = None,
    username: str = "admin",
) -> BillPayment:
    """
    Record a partial or full payment against a customer's bill.
    Validates strictly against Pending Amount (Final Deal Amount - Amount Received).
    When pending reaches zero, the bill automatically transitions to Paid.
    """
    bill = db.get(CustomerBill, bill_id)
    if not bill:
        raise ValueError("Bill not found.")

    amt = Decimal(str(payment_amount)).quantize(Decimal("0.01"))
    if amt <= Decimal("0.00"):
        raise InvalidAmountError("Payment amount must be greater than zero.")

    pending = bill.pending_amount
    if amt > pending:
        raise InvalidAmountError(
            f"Payment (₹{amt:,.2f}) exceeds Pending Amount (₹{pending:,.2f}) for Bill #{bill.bill_number}."
        )

    bill.amount_received = (bill.amount_received or Decimal("0.00")) + amt
    bill.updated_at = datetime.utcnow()

    payment = BillPayment(
        bill_id=bill.id,
        customer_id=bill.customer_id,
        amount=amt,
        payment_date=payment_date or date.today(),
        payment_method=payment_method or "Cash",
        notes=(notes or "").strip() or None,
        created_by=username,
    )
    db.add(payment)
    db.flush()

    log_activity(
        db, "RECORD_PAYMENT", "BILL_PAYMENT", str(payment.id),
        f"Collected ₹{amt:.2f} on Bill #{bill.bill_number}. Status: {bill.payment_status}",
        username=username,
    )
    return payment


def get_customer_by_id(db: Session, customer_id: int) -> Optional[Customer]:
    """Fetch full customer profile with bills, items, and payment logs."""
    q = (
        select(Customer)
        .options(
            selectinload(Customer.bills).selectinload(CustomerBill.items),
            selectinload(Customer.bills).selectinload(CustomerBill.payments),
        )
        .where(Customer.id == customer_id)
    )
    return db.execute(q).scalar_one_or_none()


def search_customers(
    db: Session,
    search: Optional[str] = None,
    status_filter: str = "All",  # 'All', 'Paid', 'Payment Pending'
    include_inactive: bool = False,
) -> List[Customer]:
    """
    Search customers by Name, Mobile, Customer ID, or Bill Number,
    and filter by overall payment status.
    """
    q = select(Customer).options(
        selectinload(Customer.bills).selectinload(CustomerBill.items),
        selectinload(Customer.bills).selectinload(CustomerBill.payments),
    )
    if not include_inactive:
        q = q.where(Customer.is_active == True)

    if search and search.strip():
        term = f"%{search.strip()}%"
        matching_bill_cids = select(CustomerBill.customer_id).where(
            CustomerBill.bill_number.ilike(term)
        )
        q = q.where(
            or_(
                Customer.name.ilike(term),
                Customer.mobile.ilike(term),
                Customer.customer_code.ilike(term),
                Customer.id.in_(matching_bill_cids),
            )
        )

    q = q.order_by(Customer.updated_at.desc(), Customer.id.desc())
    customers = list(db.execute(q).scalars().unique().all())

    if status_filter == "Paid":
        customers = [c for c in customers if c.overall_payment_status == "Paid"]
    elif status_filter == "Payment Pending":
        customers = [c for c in customers if c.overall_payment_status == "Payment Pending"]

    return customers


def get_dashboard_data(
    db: Session,
    pending_search: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Compute minimal dashboard metrics:
    - year_amount: sum of effective final amounts (amount_received when closed without pending, else final_deal_amount)
    - month_amount: sum of effective final amounts for current calendar month
    - active_customers: count of active customer records
    - pending_bills: bills where has_pending is True AND final_deal_amount > amount_received
    """
    ref = reference_date or date.today()
    effective_expr = case(
        (CustomerBill.has_pending == True, CustomerBill.final_deal_amount),
        else_=CustomerBill.amount_received,
    )

    year_amt = db.execute(
        select(func.coalesce(func.sum(effective_expr), 0))
        .join(Customer, Customer.id == CustomerBill.customer_id)
        .where(
            Customer.is_active == True,
            extract("year", CustomerBill.bill_date) == ref.year,
        )
    ).scalar() or Decimal("0.00")

    month_amt = db.execute(
        select(func.coalesce(func.sum(effective_expr), 0))
        .join(Customer, Customer.id == CustomerBill.customer_id)
        .where(
            Customer.is_active == True,
            extract("year", CustomerBill.bill_date) == ref.year,
            extract("month", CustomerBill.bill_date) == ref.month,
        )
    ).scalar() or Decimal("0.00")

    active_count = db.execute(
        select(func.count(Customer.id)).where(Customer.is_active == True)
    ).scalar() or 0

    pending_q = (
        select(CustomerBill)
        .join(Customer, Customer.id == CustomerBill.customer_id)
        .options(selectinload(CustomerBill.customer))
        .where(
            Customer.is_active == True,
            CustomerBill.has_pending == True,
            CustomerBill.final_deal_amount > CustomerBill.amount_received,
        )
        .order_by(CustomerBill.bill_date.desc(), CustomerBill.id.desc())
    )

    if pending_search and pending_search.strip():
        term = f"%{pending_search.strip()}%"
        pending_q = pending_q.where(
            or_(
                Customer.name.ilike(term),
                Customer.mobile.ilike(term),
                Customer.customer_code.ilike(term),
                Customer.address.ilike(term),
                CustomerBill.bill_number.ilike(term),
            )
        )

    pending_bills = list(db.execute(pending_q).scalars().all())

    return {
        "year_amount": Decimal(str(year_amt)),
        "month_amount": Decimal(str(month_amt)),
        "active_customers": int(active_count),
        "pending_bills": pending_bills,
    }
