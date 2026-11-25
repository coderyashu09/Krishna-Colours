"""
Automated Tests for Other Shops and Returns Management:
Product Issues, Partial Returns Flow, Stock Re-addition, and MARK AS DONE verification.
"""
import sys, os
from uuid import uuid4
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from decimal import Decimal
import pytest
from sqlalchemy import select
from config.database import get_db, init_db
from database.models import OtherShop, Product, ShopIssue, ShopIssueItem
from services.inventory_service import create_product
from services.shop_service import (
    create_shop, issue_products_to_shop, record_shop_return,
    mark_issue_as_done, IncompleteReturnError
)


def setup_module():
    init_db()


def test_other_shop_and_partial_returns_flow():
    suffix = uuid4().hex[:6].upper()
    # 1. Setup Shop and Product with 50 units
    with get_db() as db:
        shop = create_shop(
            db=db,
            shop_name=f"Mahavir Paints & Hardware {suffix}",
            owner_name="Praveen Patel",
            shop_code=f"SH-{suffix}"
        )
        sid = shop.id

        prod = create_product(
            db=db,
            name=f"Apex Floor Guard 20L {suffix}",
            category="Exterior Wall Paints",
            selling_price=Decimal("3500.00"),
            opening_stock=Decimal("50.00"),
            product_code=f"PRD-RET-{suffix}"
        )
        pid = prod.id

    # 2. Issue 10 buckets to shop
    with get_db() as db:
        issue = issue_products_to_shop(
            db=db,
            shop_id=sid,
            items_data=[{"product_id": pid, "quantity": Decimal("10.00")}],
            reference_number=f"CHALLAN-{suffix}"
        )
        assert issue.status == "PENDING"
        iid = issue.id

    # Store stock should now be 40
    with get_db() as db:
        p_chk = db.get(Product, pid)
        assert p_chk.current_stock == Decimal("40.00")
        item_obj = db.execute(
            select(ShopIssueItem).where(ShopIssueItem.issue_id == iid)
        ).scalar_one()
        item_id = item_obj.id

    # 3. Partial Return 1: Returns 6 buckets (Pending = 4)
    with get_db() as db:
        r1 = record_shop_return(
            db=db,
            issue_id=iid,
            return_items_data=[{"issue_item_id": item_id, "quantity_returned": Decimal("6.00")}]
        )
        iss1 = db.get(ShopIssue, iid)
        assert iss1.status == "PARTIALLY_RETURNED"
        # Store stock should increase to 46
        assert db.get(Product, pid).current_stock == Decimal("46.00")

    # 4. Partial Return 2: Returns 2 buckets (Pending = 2)
    with get_db() as db:
        r2 = record_shop_return(
            db=db,
            issue_id=iid,
            return_items_data=[{"issue_item_id": item_id, "quantity_returned": Decimal("2.00")}]
        )
        iss2 = db.get(ShopIssue, iid)
        assert iss2.status == "PARTIALLY_RETURNED"
        assert db.get(Product, pid).current_stock == Decimal("48.00")

    # 5. Attempt MARK AS DONE while 2 buckets are still pending -> Must fail without override!
    with get_db() as db:
        try:
            mark_issue_as_done(db=db, issue_id=iid, override_incomplete=False)
            assert False, "Should have raised IncompleteReturnError"
        except IncompleteReturnError:
            pass  # Expected behavior

    # 6. Final Return: Returns final 2 buckets (Pending = 0)
    with get_db() as db:
        r3 = record_shop_return(
            db=db,
            issue_id=iid,
            return_items_data=[{"issue_item_id": item_id, "quantity_returned": Decimal("2.00")}]
        )
        iss3 = db.get(ShopIssue, iid)
        assert iss3.status == "COMPLETED"
        assert iss3.completed_at is not None
        # Store stock should be restored to 50
        assert db.get(Product, pid).current_stock == Decimal("50.00")

    # 7. MARK AS DONE succeeds cleanly now that all items are returned
    with get_db() as db:
        done_issue = mark_issue_as_done(db=db, issue_id=iid)
        assert done_issue.status == "COMPLETED"


if __name__ == "__main__":
    setup_module()
    test_other_shop_and_partial_returns_flow()
    print("test_returns.py: ALL TESTS PASSED!")
