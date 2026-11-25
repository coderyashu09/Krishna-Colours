"""
Inventory and Stock Management Service.
Handles Product CRUD, Stock In, Stock Out, Transaction Reversals, and Low Stock Alerts.
Enforces transactional safety and prevents negative stock without authorized override.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import uuid4
from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import Session

from database.models import Product, StockTransaction, BillItem, ShopIssueItem
from services.audit_service import log_activity


class NegativeStockError(Exception):
    """Raised when an operation would lead to negative stock without authorization."""
    pass


class ProductInUseError(Exception):
    """Raised when attempting to delete a product associated with historical transactions."""
    pass


def generate_product_code(db: Session, prefix: str = "PRD-") -> str:
    """Generate next sequential product code."""
    count = db.execute(select(func.count(Product.id))).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def create_product(
    db: Session,
    name: str,
    category: str,
    brand: str = "Asian Paints",
    subcategory: Optional[str] = None,
    description: Optional[str] = None,
    unit: str = "Litre",
    purchase_price: Decimal = Decimal("0.00"),
    selling_price: Decimal = Decimal("0.00"),
    opening_stock: Decimal = Decimal("0.00"),
    min_stock_level: Decimal = Decimal("5.00"),
    product_code: Optional[str] = None,
    user_id: Optional[int] = None,
    username: str = "system",
) -> Product:
    """Create a new product with optional initial opening stock."""
    if not product_code:
        product_code = generate_product_code(db)

    # Check uniqueness
    existing = db.execute(select(Product).where(Product.product_code == product_code)).scalar_one_or_none()
    if existing:
        raise ValueError(f"Product code '{product_code}' already exists.")

    product = Product(
        product_code=product_code.strip(),
        name=name.strip(),
        brand=brand.strip() if brand else "Asian Paints",
        category=category.strip(),
        subcategory=subcategory.strip() if subcategory else None,
        description=description.strip() if description else None,
        unit=unit.strip(),
        purchase_price=Decimal(str(purchase_price)),
        selling_price=Decimal(str(selling_price)),
        current_stock=Decimal("0.00"),
        min_stock_level=Decimal(str(min_stock_level)),
        status="active",
        is_deleted=False,
    )
    db.add(product)
    db.flush()

    # If opening stock > 0, record Stock In transaction
    if Decimal(str(opening_stock)) > Decimal("0.00"):
        record_stock_in(
            db=db,
            product_id=product.id,
            quantity=Decimal(str(opening_stock)),
            purchase_price=Decimal(str(purchase_price)),
            supplier_name="Opening Stock",
            invoice_number="OPENING",
            notes="Initial opening stock during product creation",
            user_id=user_id,
            username=username,
        )

    log_activity(
        db=db,
        action="CREATE_PRODUCT",
        record_type="PRODUCT",
        record_id=str(product.id),
        details=f"Created product '{product.name}' ({product.product_code}), Category: {product.category}",
        user_id=user_id,
        username=username,
    )
    return product


def update_product(
    db: Session,
    product_id: int,
    name: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    subcategory: Optional[str] = None,
    description: Optional[str] = None,
    unit: Optional[str] = None,
    purchase_price: Optional[Decimal] = None,
    selling_price: Optional[Decimal] = None,
    min_stock_level: Optional[Decimal] = None,
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    username: str = "system",
) -> Product:
    """Update existing product details."""
    product = db.execute(select(Product).where(Product.id == product_id)).scalar_one_or_none()
    if not product:
        raise ValueError(f"Product with ID {product_id} not found.")

    changes = []
    if name is not None and name != product.name:
        changes.append(f"Name: {product.name} -> {name}")
        product.name = name.strip()
    if category is not None and category != product.category:
        changes.append(f"Category: {product.category} -> {category}")
        product.category = category.strip()
    if brand is not None:
        product.brand = brand.strip()
    if subcategory is not None:
        product.subcategory = subcategory.strip() if subcategory else None
    if description is not None:
        product.description = description.strip() if description else None
    if unit is not None:
        product.unit = unit.strip()
    if purchase_price is not None:
        new_pp = Decimal(str(purchase_price))
        if new_pp != product.purchase_price:
            changes.append(f"Purchase Price: {product.purchase_price} -> {new_pp}")
            product.purchase_price = new_pp
    if selling_price is not None:
        new_sp = Decimal(str(selling_price))
        if new_sp != product.selling_price:
            changes.append(f"Selling Price: {product.selling_price} -> {new_sp}")
            product.selling_price = new_sp
    if min_stock_level is not None:
        product.min_stock_level = Decimal(str(min_stock_level))
    if status is not None:
        product.status = status

    product.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db=db,
        action="UPDATE_PRODUCT",
        record_type="PRODUCT",
        record_id=str(product.id),
        details=f"Updated product '{product.name}': " + ("; ".join(changes) if changes else "metadata updated"),
        user_id=user_id,
        username=username,
    )
    return product


def delete_product(
    db: Session,
    product_id: int,
    user_id: Optional[int] = None,
    username: str = "system",
) -> bool:
    """
    Safely delete or soft-delete a product.
    If the product has historical bills, stock movements, or shop issues, soft-delete it.
    """
    product = db.execute(select(Product).where(Product.id == product_id)).scalar_one_or_none()
    if not product:
        raise ValueError(f"Product with ID {product_id} not found.")

    # Check for historical transactions
    has_bills = db.execute(select(func.count(BillItem.id)).where(BillItem.product_id == product_id)).scalar() or 0
    has_stock_tx = db.execute(select(func.count(StockTransaction.id)).where(StockTransaction.product_id == product_id)).scalar() or 0
    has_shop_issues = db.execute(select(func.count(ShopIssueItem.id)).where(ShopIssueItem.product_id == product_id)).scalar() or 0

    if has_bills > 0 or has_stock_tx > 0 or has_shop_issues > 0:
        # Soft-delete to preserve relational integrity & accounting history
        product.is_deleted = True
        product.status = "discontinued"
        product.updated_at = datetime.utcnow()
        db.flush()
        action_msg = "Soft-deleted (deactivated) due to existing historical records"
    else:
        # Hard delete safely if no transaction history
        db.delete(product)
        db.flush()
        action_msg = "Hard-deleted (no history attached)"

    log_activity(
        db=db,
        action="DELETE_PRODUCT",
        record_type="PRODUCT",
        record_id=str(product_id),
        details=f"Product '{product.name}' ({product.product_code}): {action_msg}",
        user_id=user_id,
        username=username,
    )
    return True


def get_products(
    db: Session,
    search: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    stock_status: Optional[str] = None,  # 'ALL', 'IN_STOCK', 'LOW_STOCK', 'OUT_OF_STOCK'
    include_deleted: bool = False,
) -> List[Product]:
    """Search and filter products catalog."""
    query = select(Product)
    if not include_deleted:
        query = query.where(Product.is_deleted == False)

    if category and category != "All":
        query = query.where(Product.category == category)
    if brand and brand != "All":
        query = query.where(Product.brand == brand)

    if search:
        search_term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Product.name.ilike(search_term),
                Product.product_code.ilike(search_term),
                Product.description.ilike(search_term),
                Product.subcategory.ilike(search_term),
            )
        )

    if stock_status == "IN_STOCK":
        query = query.where(Product.current_stock > Product.min_stock_level)
    elif stock_status == "LOW_STOCK":
        query = query.where(and_(Product.current_stock > 0, Product.current_stock <= Product.min_stock_level))
    elif stock_status == "OUT_OF_STOCK":
        query = query.where(Product.current_stock <= 0)

    query = query.order_by(Product.name.asc())
    return list(db.execute(query).scalars().all())


def record_stock_in(
    db: Session,
    product_id: int,
    quantity: Decimal,
    purchase_price: Optional[Decimal] = None,
    supplier_name: Optional[str] = None,
    invoice_number: Optional[str] = None,
    notes: Optional[str] = None,
    user_id: Optional[int] = None,
    username: str = "system",
) -> StockTransaction:
    """Record products received into stock."""
    product = db.execute(select(Product).where(Product.id == product_id)).scalar_one_or_none()
    if not product:
        raise ValueError(f"Product with ID {product_id} not found.")

    qty = Decimal(str(quantity))
    if qty <= Decimal("0.00"):
        raise ValueError("Stock In quantity must be greater than zero.")

    unit_p = Decimal(str(purchase_price)) if purchase_price is not None else product.purchase_price

    # Generate transaction code
    tx_code = f"STX-IN-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:4].upper()}"

    tx = StockTransaction(
        transaction_code=tx_code,
        transaction_type="STOCK_IN",
        product_id=product.id,
        quantity=qty,
        unit_price=unit_p,
        reference_type="SUPPLIER_INVOICE" if invoice_number else "MANUAL",
        reference_id=invoice_number,
        party_name=supplier_name,
        notes=notes,
        created_by_user_id=user_id,
        is_cancelled=False,
        created_at=datetime.utcnow()
    )
    db.add(tx)

    # Increment stock
    product.current_stock = product.current_stock + qty
    if purchase_price is not None and purchase_price > Decimal("0.00"):
        product.purchase_price = unit_p
    product.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db=db,
        action="STOCK_IN",
        record_type="STOCK",
        record_id=str(tx.id),
        details=f"Added {qty} {product.unit} to '{product.name}' (Inv: {invoice_number or 'N/A'}, Supplier: {supplier_name or 'N/A'}). New stock: {product.current_stock}",
        user_id=user_id,
        username=username,
    )
    return tx


def record_stock_out(
    db: Session,
    product_id: int,
    quantity: Decimal,
    selling_price: Optional[Decimal] = None,
    party_name: Optional[str] = None,
    reference_type: str = "MANUAL",
    reference_id: Optional[str] = None,
    notes: Optional[str] = None,
    override_negative: bool = False,
    user_id: Optional[int] = None,
    username: str = "system",
) -> StockTransaction:
    """
    Record products leaving stock (sale, manual issue, wastage, etc.).
    Prevents negative stock unless authorized override is True.
    """
    product = db.execute(select(Product).where(Product.id == product_id)).scalar_one_or_none()
    if not product:
        raise ValueError(f"Product with ID {product_id} not found.")

    qty = Decimal(str(quantity))
    if qty <= Decimal("0.00"):
        raise ValueError("Stock Out quantity must be greater than zero.")

    if not override_negative and (product.current_stock - qty) < Decimal("0.00"):
        raise NegativeStockError(
            f"Insufficient stock for '{product.name}'. Current stock: {product.current_stock} {product.unit}, Requested: {qty} {product.unit}."
        )

    unit_p = Decimal(str(selling_price)) if selling_price is not None else product.selling_price

    tx_code = f"STX-OUT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:4].upper()}"

    tx = StockTransaction(
        transaction_code=tx_code,
        transaction_type="STOCK_OUT",
        product_id=product.id,
        quantity=qty,
        unit_price=unit_p,
        reference_type=reference_type,
        reference_id=reference_id,
        party_name=party_name,
        notes=notes,
        created_by_user_id=user_id,
        is_cancelled=False,
        created_at=datetime.utcnow()
    )
    db.add(tx)

    # Decrement stock
    product.current_stock = product.current_stock - qty
    product.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db=db,
        action="STOCK_OUT",
        record_type="STOCK",
        record_id=str(tx.id),
        details=f"Deducted {qty} {product.unit} from '{product.name}' (Ref: {reference_id or 'N/A'}, Party: {party_name or 'N/A'}). Remaining stock: {product.current_stock}",
        user_id=user_id,
        username=username,
    )
    return tx


def cancel_stock_transaction(
    db: Session,
    transaction_id: int,
    reason: str,
    override_negative: bool = False,
    user_id: Optional[int] = None,
    username: str = "system",
) -> StockTransaction:
    """
    Cancel a stock transaction and reverse its inventory effect exactly once.
    """
    tx = db.execute(select(StockTransaction).where(StockTransaction.id == transaction_id)).scalar_one_or_none()
    if not tx:
        raise ValueError(f"Stock transaction {transaction_id} not found.")

    if tx.is_cancelled:
        raise ValueError(f"Transaction {tx.transaction_code} is already cancelled.")

    product = db.execute(select(Product).where(Product.id == tx.product_id)).scalar_one()

    # Reverse inventory effect
    if tx.transaction_type in ("STOCK_IN", "SHOP_RETURN"):
        # Previous transaction added stock; reversing subtracts it
        if not override_negative and (product.current_stock - tx.quantity) < Decimal("0.00"):
            raise NegativeStockError(
                f"Cannot cancel Stock In: Reversing would reduce '{product.name}' stock to {product.current_stock - tx.quantity} (negative)."
            )
        product.current_stock = product.current_stock - tx.quantity
    elif tx.transaction_type in ("STOCK_OUT", "BILL_SALE", "SHOP_ISSUE"):
        # Previous transaction subtracted stock; reversing adds it back
        product.current_stock = product.current_stock + tx.quantity

    tx.is_cancelled = True
    tx.notes = f"{tx.notes or ''} [CANCELLED: {reason}]"
    product.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db=db,
        action="CANCEL_STOCK_TRANSACTION",
        record_type="STOCK",
        record_id=str(tx.id),
        details=f"Cancelled {tx.transaction_code} ({tx.transaction_type} of {tx.quantity} {product.unit}). Reversal applied. Reason: {reason}",
        user_id=user_id,
        username=username,
    )
    return tx


def get_low_stock_alerts(db: Session) -> Dict[str, List[Product]]:
    """Return categorized low stock alerts."""
    out_of_stock = list(
        db.execute(
            select(Product).where(and_(Product.is_deleted == False, Product.current_stock <= 0)).order_by(Product.name.asc())
        ).scalars().all()
    )
    low_stock = list(
        db.execute(
            select(Product).where(
                and_(
                    Product.is_deleted == False,
                    Product.current_stock > 0,
                    Product.current_stock <= Product.min_stock_level
                )
            ).order_by(Product.current_stock.asc())
        ).scalars().all()
    )
    return {
        "out_of_stock": out_of_stock,
        "low_stock": low_stock,
        "total_alerts": len(out_of_stock) + len(low_stock)
    }
