"""
Automated Tests for Inventory Management: Product CRUD, Stock In, Stock Out,
Negative Stock Prevention, and Transaction Reversals.
"""
import sys, os
from uuid import uuid4
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from decimal import Decimal
import pytest
from config.database import get_db, init_db
from database.models import Product, StockTransaction
from services.inventory_service import (
    create_product, update_product, delete_product, record_stock_in,
    record_stock_out, cancel_stock_transaction, get_products,
    get_low_stock_alerts, NegativeStockError
)


def setup_module():
    init_db()


def test_product_crud_and_stock_flow():
    test_code = f"TEST-APEX-{uuid4().hex[:6].upper()}"
    with get_db() as db:
        # 1. Create Product
        p = create_product(
            db=db,
            name=f"Apex Ultima Brilliant White 20L {test_code}",
            category="Exterior Wall Paints",
            brand="Asian Paints",
            unit="Litre",
            purchase_price=Decimal("4200.00"),
            selling_price=Decimal("4950.00"),
            opening_stock=Decimal("10.00"),
            min_stock_level=Decimal("3.00"),
            product_code=test_code,
        )
        assert p.id is not None
        assert p.current_stock == Decimal("10.00")
        pid = p.id

    with get_db() as db:
        # 2. Stock In: Add 5 more
        tx_in = record_stock_in(
            db=db,
            product_id=pid,
            quantity=Decimal("5.00"),
            purchase_price=Decimal("4200.00"),
            supplier_name="Asian Paints Depot",
            invoice_number="INV-TEST-001"
        )
        assert tx_in.quantity == Decimal("5.00")
        prod = db.get(Product, pid)
        assert prod.current_stock == Decimal("15.00")

    with get_db() as db:
        # 3. Stock Out: Deduct 4
        tx_out = record_stock_out(
            db=db,
            product_id=pid,
            quantity=Decimal("4.00"),
            selling_price=Decimal("4950.00"),
            party_name="Contractor Test",
        )
        assert tx_out.quantity == Decimal("4.00")
        prod = db.get(Product, pid)
        assert prod.current_stock == Decimal("11.00")

    with get_db() as db:
        # 4. Negative Stock Prevention
        try:
            record_stock_out(
                db=db,
                product_id=pid,
                quantity=Decimal("50.00"),  # Only 11 available
                override_negative=False
            )
            assert False, "Should have raised NegativeStockError"
        except NegativeStockError:
            pass  # Expected behavior

        # With admin override it should succeed
        tx_override = record_stock_out(
            db=db,
            product_id=pid,
            quantity=Decimal("15.00"),
            override_negative=True
        )
        prod = db.get(Product, pid)
        assert prod.current_stock == Decimal("-4.00")

    with get_db() as db:
        # 5. Reverse the override transaction
        cancelled = cancel_stock_transaction(
            db=db,
            transaction_id=tx_override.id,
            reason="Testing cancellation",
            override_negative=True
        )
        assert cancelled.is_cancelled is True
        prod = db.get(Product, pid)
        assert prod.current_stock == Decimal("11.00")

    with get_db() as db:
        # 6. Check Low Stock alerts
        prod = db.get(Product, pid)
        prod.current_stock = Decimal("2.00")  # Less than min_stock_level (3.00)
        db.flush()
        alerts = get_low_stock_alerts(db)
        assert any(p.id == pid for p in alerts["low_stock"])


if __name__ == "__main__":
    setup_module()
    test_product_crud_and_stock_flow()
    print("test_inventory.py: ALL TESTS PASSED!")
