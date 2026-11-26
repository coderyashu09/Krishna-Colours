"""
Comprehensive Tests for Krishna Colour – Asian Paints Customer Management System.
Runs against an isolated in-memory SQLite database so production data is never polluted.
Tests every single requirement in Section 13 and Updated Requirements Section 5.
"""
import sys
import os
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import (
    Base,
    ItemCategory,
    ItemProduct,
    ItemPackSize,
    Customer,
    CustomerBill,
    BillItem,
)
from database.seed_asian_paints import seed_initial_dropdown_items
from services.customer_service import (
    create_customer,
    update_customer_details,
    add_bill_to_customer,
    update_bill,
    record_bill_payment,
    search_customers,
    get_dashboard_data,
    get_customer_by_id,
    DuplicateBillNumberError,
    DuplicateCustomerError,
    InvalidAmountError,
)
from services.item_service import (
    get_categories,
    get_products_for_category,
    get_pack_sizes_for_product,
    add_category,
    add_product,
    rename_product,
    add_pack_size,
    rename_pack_size,
    remove_or_archive_product,
    delete_or_archive_category,
    is_product_used_in_bills,
)


def _new_test_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    seed_initial_dropdown_items(db, force=True)
    db.commit()
    return db


def test_initial_asian_paints_dropdown_catalog():
    db = _new_test_session()
    try:
        cats = get_categories(db)
        assert [c.name for c in cats] == [
            "Interior colour",
            "Exterior colour",
            "Exterior primer",
            "Interior primer",
        ]
        all_prods = db.query(ItemProduct).all()
        assert len(all_prods) == 15
        prod_names = {p.name for p in all_prods}
        assert "Damp shith" in prod_names
        assert "Sprac interior primer" in prod_names
        assert "St primer" in prod_names
        assert "Royal matt" in prod_names

        sizes = db.query(ItemPackSize).all()
        assert len(sizes) == 60
        for p in all_prods:
            assert [s.size_label for s in p.pack_sizes] == ["1 L", "4 L", "10 L", "20 L"]
    finally:
        db.close()


def test_bargaining_final_deal_and_payment_cases():
    """
    Tests 2-amount + optional pending logic:
    1. Final Deal ₹300, Received ₹250, has_pending=False -> Paid, pending 0, effective final = ₹250 (received is final!)
    2. Final Deal ₹250, Received ₹150, has_pending=True  -> Payment Pending, ₹100 pending
    3. Final Deal ₹500, Received ₹500, has_pending=True  -> Paid (no pending amount -> done)
    4. Pending list contains ONLY bills with has_pending=True and pending > 0
    5. Paying pending bill in full removes it from pending list while retaining history
    6. Year Amount & Month Amount sum effective final amounts (₹250 + ₹250 + ₹500 = ₹1000)
    """
    db = _new_test_session()
    try:
        cat_int = db.query(ItemCategory).filter_by(name="Interior colour").one()
        prod_te = db.query(ItemProduct).filter_by(category_id=cat_int.id, name="Tractor emulsion").one()
        ps_4l = db.query(ItemPackSize).filter_by(product_id=prod_te.id, size_label="4 L").one()

        c1 = create_customer(
            db=db,
            name="Rahul Patel",
            mobile="9876543210",
            address="Rajkot",
            bills_data=[
                {
                    "bill_number": "244",
                    "bill_date": date(2026, 11, 20),
                    "final_deal_amount": Decimal("300.00"),
                    "amount_received": Decimal("250.00"),
                    "has_pending": False,
                    "items": [
                        {
                            "entry_type": "DROPDOWN",
                            "category_id": cat_int.id,
                            "product_id": prod_te.id,
                            "pack_size_id": ps_4l.id,
                            "quantity": Decimal("1"),
                        }
                    ],
                },
                {
                    "bill_number": "245",
                    "bill_date": date(2026, 11, 21),
                    "final_deal_amount": Decimal("250.00"),
                    "amount_received": Decimal("150.00"),
                    "has_pending": True,
                    "items": [
                        {
                            "entry_type": "CUSTOM",
                            "product_name": "Wall putty",
                            "pack_size": "5 kg",
                            "quantity": Decimal("2"),
                        }
                    ],
                },
                {
                    "bill_number": "12540",
                    "bill_date": date(2026, 1, 15),
                    "final_deal_amount": Decimal("500.00"),
                    "amount_received": Decimal("500.00"),
                    "has_pending": True,
                    "items": [],
                },
            ],
        )
        db.commit()

        assert c1.customer_code == "KC-000001"
        bills_by_no = {b.bill_number: b for b in c1.bills}
        assert bills_by_no["244"].pending_amount == Decimal("0.00")
        assert bills_by_no["244"].effective_final_amount == Decimal("250.00")
        assert bills_by_no["244"].payment_status == "Paid"

        assert bills_by_no["245"].pending_amount == Decimal("100.00")
        assert bills_by_no["245"].payment_status == "Payment Pending"

        assert bills_by_no["12540"].pending_amount == Decimal("0.00")
        assert bills_by_no["12540"].payment_status == "Paid"

        assert c1.total_final_deal_amount == Decimal("1000.00")
        assert c1.total_amount_received == Decimal("900.00")
        assert c1.total_pending_amount == Decimal("100.00")

        dash_nov = get_dashboard_data(db, reference_date=date(2026, 11, 26))
        assert dash_nov["year_amount"] == Decimal("1000.00")
        assert dash_nov["month_amount"] == Decimal("500.00")
        assert dash_nov["active_customers"] == 1
        assert len(dash_nov["pending_bills"]) == 1
        assert dash_nov["pending_bills"][0].bill_number == "245"

        try:
            record_bill_payment(db, bills_by_no["245"].id, Decimal("150.00"))
            assert False, "Should block payment exceeding pending amount"
        except InvalidAmountError:
            pass

        record_bill_payment(db, bills_by_no["245"].id, Decimal("100.00"), payment_method="UPI")
        db.commit()

        dash_after = get_dashboard_data(db, reference_date=date(2026, 11, 26))
        assert len(dash_after["pending_bills"]) == 0
        refreshed = get_customer_by_id(db, c1.id)
        assert refreshed.overall_payment_status == "Paid"
        assert len(refreshed.bills) == 3
        assert len([b for b in refreshed.bills if b.bill_number == "245"][0].payments) == 2
    finally:
        db.close()


def test_duplicate_prevention_search_and_editing():
    db = _new_test_session()
    try:
        c1 = create_customer(
            db, name="Amit Shah", mobile="9988776655", address="Surat",
            bills_data=[
                {
                    "bill_number": "246",
                    "bill_date": date(2026, 11, 25),
                    "final_deal_amount": Decimal("800.00"),
                    "amount_received": Decimal("500.00"),
                    "has_pending": True,
                    "items": [{"entry_type": "CUSTOM", "product_name": "Primer Coat", "quantity": Decimal("1")}],
                }
            ],
        )
        db.commit()

        try:
            create_customer(db, name="Amit Dup", mobile="9988776655", address="Surat")
            assert False, "Duplicate mobile should be rejected"
        except DuplicateCustomerError:
            pass

        try:
            add_bill_to_customer(
                db, c1.id, "246", date.today(), Decimal("200"), Decimal("100"), []
            )
            assert False, "Duplicate bill number for same customer should be rejected"
        except DuplicateBillNumberError:
            pass

        bill_246 = c1.bills[0]
        update_bill(
            db,
            bill_id=bill_246.id,
            bill_number="246-A",
            bill_date=bill_246.bill_date,
            final_deal_amount=Decimal("800.00"),
            amount_received=Decimal("500.00"),
            has_pending=True,
        )
        db.commit()
        assert bill_246.final_deal_amount == Decimal("800.00")
        assert bill_246.pending_amount == Decimal("300.00")

        assert len(search_customers(db, search="Amit")) == 1
        assert len(search_customers(db, search="9988776655")) == 1
        assert len(search_customers(db, search="KC-000001")) == 1
        assert len(search_customers(db, search="246-A")) == 1
        assert len(search_customers(db, status_filter="Payment Pending")) == 1
        assert len(search_customers(db, status_filter="Paid")) == 0
    finally:
        db.close()


def test_admin_item_management_and_history_preservation():
    db = _new_test_session()
    try:
        cat = add_category(db, "Wood Finishes")
        prod = add_product(db, cat.id, "Melamyne Gold", pack_sizes=["1 L", "4 L"])
        ps_1l = get_pack_sizes_for_product(db, prod.id)[0]
        add_pack_size(db, prod.id, "500 ml")
        rename_pack_size(db, ps_1l.id, "1 Litre")

        cust = create_customer(
            db,
            name="Meera Enterprise",
            mobile="9123456789",
            address="Ahmedabad",
            bills_data=[
                {
                    "bill_number": "701",
                    "bill_date": date.today(),
                    "final_deal_amount": Decimal("350"),
                    "amount_received": Decimal("350"),
                    "has_pending": False,
                    "items": [
                        {
                            "entry_type": "DROPDOWN",
                            "category_id": cat.id,
                            "product_id": prod.id,
                            "pack_size_id": ps_1l.id,
                            "quantity": Decimal("2"),
                        }
                    ],
                }
            ],
        )
        db.commit()

        assert is_product_used_in_bills(db, prod.id) == 1

        # Rename product -> historical bill item snapshot stays intact!
        rename_product(db, prod.id, "Melamyne Gloss")
        db.commit()
        assert cust.bills[0].items[0].product_name == "Melamyne Gold"

        # Archive/remove used product -> archives cleanly & hides from active dropdown
        action, _ = remove_or_archive_product(db, prod.id, archive_only=False)
        db.commit()
        assert action == "archived"
        assert len(get_products_for_category(db, cat.id, include_inactive=False)) == 0
        # Customer history remains completely intact
        assert cust.bills[0].items[0].product_name == "Melamyne Gold"

        # Archiving used category preserves records; deleting unused category deletes cleanly
        cat_act, _ = delete_or_archive_category(db, cat.id, archive_if_used=True)
        assert cat_act == "archived"
        unused_cat = add_category(db, "Temp Unused")
        u_act, _ = delete_or_archive_category(db, unused_cat.id, archive_if_used=True)
        assert u_act == "deleted"
    finally:
        db.close()
