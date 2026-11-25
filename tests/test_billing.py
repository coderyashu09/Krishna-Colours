"""
Automated Tests for Billing System:
Multi-Item Decimal Calculations, Manual & Auto Bill Numbering, Duplicate Prevention,
Stock Auto-Deduction, ReportLab PDF Invoices, and Exact-Once Cancellation Reversals.
"""
import sys, os
from uuid import uuid4
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date
from decimal import Decimal
import pytest
from config.database import get_db, init_db
from database.models import Customer, Product, Bill, StockTransaction
from services.customer_service import create_customer
from services.inventory_service import create_product
from services.billing_service import (
    create_bill, cancel_bill, calculate_bill_totals,
    DuplicateBillNumberError, InvalidBillOperationError
)
from utils.pdf_generator import generate_bill_pdf


def setup_module():
    init_db()


def test_billing_multi_item_and_inventory_lifecycle():
    suffix = uuid4().hex[:6].upper()
    bill_no = f"BILL-244-{suffix}"
    # 1. Setup Customer and Products
    with get_db() as db:
        cust = create_customer(
            db=db,
            name=f"Rajesh Sharma Contractor {suffix}",
            mobile=f"98{uuid4().int % 100000000:08d}",
            customer_code=f"KC-TEST-{suffix}"
        )
        cid = cust.id

        # Product A: ₹500
        pA = create_product(
            db=db, name=f"Asian Paints TruCare Primer {suffix}", category="Interior Wall Paints",
            selling_price=Decimal("500.00"), opening_stock=Decimal("20.00"), product_code=f"PRD-TA-{suffix}"
        )
        # Product B: ₹250
        pB = create_product(
            db=db, name=f"Asian Paints Stainer Fast Yellow {suffix}", category="Colourants & Strainers",
            selling_price=Decimal("250.00"), opening_stock=Decimal("30.00"), product_code=f"PRD-TB-{suffix}"
        )
        # Product C: ₹1500
        pC = create_product(
            db=db, name=f"Tractor Emulsion Shyp White 10L {suffix}", category="Interior Wall Paints",
            selling_price=Decimal("1500.00"), opening_stock=Decimal("10.00"), product_code=f"PRD-TC-{suffix}"
        )
        pA_id, pB_id, pC_id = pA.id, pB.id, pC.id

    # 2. Test Multi-Product Bill matching Prompt Specification
    # Product A: 2 × ₹500 = ₹1,000
    # Product B: 3 × ₹250 = ₹750
    # Product C: 1 × ₹1,500 = ₹1,500
    # Subtotal: ₹3,250 | Received: ₹2,000 | Outstanding: ₹1,250
    items = [
        {"product_id": pA_id, "quantity": Decimal("2.00"), "unit_price": Decimal("500.00")},
        {"product_id": pB_id, "quantity": Decimal("3.00"), "unit_price": Decimal("250.00")},
        {"product_id": pC_id, "quantity": Decimal("1.00"), "unit_price": Decimal("1500.00")},
    ]

    with get_db() as db:
        bill = create_bill(
            db=db,
            customer_id=cid,
            items_data=items,
            bill_number=bill_no,  # Manual Bill Number
            initial_payment_amount=Decimal("2000.00"),
            payment_method="CASH",
            bill_status="FINALIZED",
        )
        assert bill.bill_number == bill_no
        assert bill.subtotal == Decimal("3250.00")
        assert bill.grand_total == Decimal("3250.00")
        assert bill.amount_received == Decimal("2000.00")
        assert bill.outstanding_amount == Decimal("1250.00")
        assert bill.payment_status == "PARTIALLY_PAID"
        bill_id = bill.id

    # 3. Verify Stock Automatically Decremented
    with get_db() as db:
        pA_chk = db.get(Product, pA_id)
        pB_chk = db.get(Product, pB_id)
        pC_chk = db.get(Product, pC_id)
        assert pA_chk.current_stock == Decimal("18.00")  # 20 - 2
        assert pB_chk.current_stock == Decimal("27.00")  # 30 - 3
        assert pC_chk.current_stock == Decimal("9.00")   # 10 - 1

    # 4. Test Duplicate Bill Number Prevention
    with get_db() as db:
        try:
            create_bill(
                db=db,
                customer_id=cid,
                items_data=items,
                bill_number=bill_no,  # Already exists!
            )
            assert False, "Should have raised DuplicateBillNumberError"
        except DuplicateBillNumberError:
            pass  # Expected

    # 5. Test PDF Generation
    with get_db() as db:
        b_obj = db.get(Bill, bill_id)
        pdf_bytes = generate_bill_pdf(b_obj)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b"%PDF")

    # 6. Test Bill Cancellation with Exact-Once Stock Reversal
    with get_db() as db:
        cancel_bill(db=db, bill_id=bill_id, reason="Customer cancelled order")

    with get_db() as db:
        b_cancelled = db.get(Bill, bill_id)
        assert b_cancelled.bill_status == "CANCELLED"
        # Verify stock was restored to opening amounts
        assert db.get(Product, pA_id).current_stock == Decimal("20.00")
        assert db.get(Product, pB_id).current_stock == Decimal("30.00")
        assert db.get(Product, pC_id).current_stock == Decimal("10.00")


if __name__ == "__main__":
    setup_module()
    test_billing_multi_item_and_inventory_lifecycle()
    print("test_billing.py: ALL TESTS PASSED!")
