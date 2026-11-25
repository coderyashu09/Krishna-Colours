"""
Automated Tests for Payments:
Multiple payments per bill, Partial payments, Overpayment prevention,
Payment reversals, and Customer Ledger Statements.
"""
import sys, os
from uuid import uuid4
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from decimal import Decimal
import pytest
from config.database import get_db, init_db
from database.models import Customer, Product, Bill, Payment
from services.customer_service import create_customer
from services.inventory_service import create_product
from services.billing_service import create_bill
from services.payment_service import (
    record_payment, reverse_payment, get_customer_statement, OverpaymentError
)


def setup_module():
    init_db()


def test_payment_tracking_and_overpayment_prevention():
    suffix = uuid4().hex[:6].upper()
    # 1. Setup Customer and Bill of ₹10,000 (as in prompt section 11)
    with get_db() as db:
        cust = create_customer(
            db=db,
            name=f"Vijay Builders {suffix}",
            mobile=f"98{uuid4().int % 100000000:08d}",
            customer_code=f"KC-PAY-{suffix}"
        )
        cid = cust.id

        prod = create_product(
            db=db,
            name=f"Royale Luxury Matte 20L {suffix}",
            category="Interior Wall Paints",
            selling_price=Decimal("10000.00"),
            opening_stock=Decimal("10.00"),
            product_code=f"PRD-PAY-{suffix}"
        )
        pid = prod.id

        bill = create_bill(
            db=db,
            customer_id=cid,
            items_data=[{"product_id": pid, "quantity": Decimal("1.00"), "unit_price": Decimal("10000.00")}],
            bill_number=f"BILL-10K-{suffix}",
            initial_payment_amount=Decimal("0.00"),  # Fully unpaid
        )
        assert bill.grand_total == Decimal("10000.00")
        assert bill.outstanding_amount == Decimal("10000.00")
        bid = bill.id

    # 2. Payment 1 = ₹2,000
    with get_db() as db:
        p1 = record_payment(db=db, customer_id=cid, bill_id=bid, amount=Decimal("2000.00"), payment_method="CASH")
        b1 = db.get(Bill, bid)
        assert b1.amount_received == Decimal("2000.00")
        assert b1.outstanding_amount == Decimal("8000.00")
        assert b1.payment_status == "PARTIALLY_PAID"

    # 3. Payment 2 = ₹3,000
    with get_db() as db:
        p2 = record_payment(db=db, customer_id=cid, bill_id=bid, amount=Decimal("3000.00"), payment_method="UPI")
        b2 = db.get(Bill, bid)
        assert b2.amount_received == Decimal("5000.00")
        assert b2.outstanding_amount == Decimal("5000.00")

    # 4. Payment 3 = ₹2,000
    # Total received = ₹7,000 | Outstanding = ₹3,000
    with get_db() as db:
        p3 = record_payment(db=db, customer_id=cid, bill_id=bid, amount=Decimal("2000.00"), payment_method="BANK_TRANSFER")
        b3 = db.get(Bill, bid)
        assert b3.amount_received == Decimal("7000.00")
        assert b3.outstanding_amount == Decimal("3000.00")
        p3_id = p3.id

    # 5. Overpayment Prevention: Paying ₹5,000 when only ₹3,000 is outstanding should raise OverpaymentError
    with get_db() as db:
        try:
            record_payment(
                db=db, customer_id=cid, bill_id=bid, amount=Decimal("5000.00"), allow_overpayment=False
            )
            assert False, "Should have raised OverpaymentError"
        except OverpaymentError:
            pass  # Expected behavior

    # 6. Payment Reversal: Reverse Payment 3 (₹2,000)
    with get_db() as db:
        rev = reverse_payment(db=db, payment_id=p3_id, reason="Cheque bounced / reversal test")
        assert rev.is_reversal is True
        b_rev = db.get(Bill, bid)
        # Outstanding balance should now be ₹5,000 again
        assert b_rev.amount_received == Decimal("5000.00")
        assert b_rev.outstanding_amount == Decimal("5000.00")

    # 7. Customer Statement Verification
    with get_db() as db:
        statement = get_customer_statement(db, cid)
        assert statement["total_billed"] == Decimal("10000.00")
        assert statement["total_paid"] == Decimal("5000.00")
        assert statement["net_outstanding"] == Decimal("5000.00")


if __name__ == "__main__":
    setup_module()
    test_payment_tracking_and_overpayment_prevention()
    print("test_payments.py: ALL TESTS PASSED!")
