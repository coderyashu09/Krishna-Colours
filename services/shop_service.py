"""
Other Shops and Return Management Service.
Handles shop profiles, issuing products to other shops (stock reduction),
recording partial or full returns (stock addition), and explicit MARK AS DONE verification.
Completed transactions are permanently preserved in history.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import uuid4
from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import Session

from database.models import OtherShop, ShopIssue, ShopIssueItem, ShopReturn, ShopReturnItem, Product, StockTransaction
from services.audit_service import log_activity
from services.inventory_service import NegativeStockError


class IncompleteReturnError(Exception):
    """Raised when trying to mark an issue as done while items remain unreturned."""
    pass


def generate_shop_code(db: Session, prefix: str = "SHOP-") -> str:
    """Generate sequential shop identifier."""
    count = db.execute(select(func.count(OtherShop.id))).scalar() or 0
    return f"{prefix}{count + 1:03d}"


def create_shop(
    db: Session,
    shop_name: str,
    owner_name: Optional[str] = None,
    mobile: Optional[str] = None,
    address: Optional[str] = None,
    notes: Optional[str] = None,
    shop_code: Optional[str] = None,
    user_id: Optional[int] = None,
    username: str = "system",
) -> OtherShop:
    """Register a new partner shop."""
    if not shop_code:
        shop_code = generate_shop_code(db)

    existing = db.execute(select(OtherShop).where(OtherShop.shop_code == shop_code)).scalar_one_or_none()
    if existing:
        raise ValueError(f"Shop code '{shop_code}' already exists.")

    shop = OtherShop(
        shop_code=shop_code.strip(),
        shop_name=shop_name.strip(),
        owner_name=owner_name.strip() if owner_name else None,
        mobile=mobile.strip() if mobile else None,
        address=address.strip() if address else None,
        notes=notes.strip() if notes else None,
        status="active",
        is_deleted=False,
    )
    db.add(shop)
    db.flush()

    log_activity(
        db=db,
        action="CREATE_SHOP",
        record_type="SHOP",
        record_id=str(shop.id),
        details=f"Created shop '{shop.shop_name}' ({shop.shop_code}), Owner: {shop.owner_name or 'N/A'}",
        user_id=user_id,
        username=username,
    )
    return shop


def update_shop(
    db: Session,
    shop_id: int,
    shop_name: Optional[str] = None,
    owner_name: Optional[str] = None,
    mobile: Optional[str] = None,
    address: Optional[str] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    username: str = "system",
) -> OtherShop:
    """Update partner shop details."""
    shop = db.execute(select(OtherShop).where(OtherShop.id == shop_id)).scalar_one_or_none()
    if not shop:
        raise ValueError(f"Shop with ID {shop_id} not found.")

    if shop_name is not None:
        shop.shop_name = shop_name.strip()
    if owner_name is not None:
        shop.owner_name = owner_name.strip() if owner_name else None
    if mobile is not None:
        shop.mobile = mobile.strip() if mobile else None
    if address is not None:
        shop.address = address.strip() if address else None
    if notes is not None:
        shop.notes = notes.strip() if notes else None
    if status is not None:
        shop.status = status

    shop.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db=db,
        action="UPDATE_SHOP",
        record_type="SHOP",
        record_id=str(shop.id),
        details=f"Updated shop details for '{shop.shop_name}' ({shop.shop_code})",
        user_id=user_id,
        username=username,
    )
    return shop


def delete_shop(
    db: Session,
    shop_id: int,
    user_id: Optional[int] = None,
    username: str = "system",
) -> bool:
    """Soft-delete partner shop to protect transaction records."""
    shop = db.execute(select(OtherShop).where(OtherShop.id == shop_id)).scalar_one_or_none()
    if not shop:
        raise ValueError(f"Shop with ID {shop_id} not found.")

    shop.is_deleted = True
    shop.status = "inactive"
    shop.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db=db,
        action="DELETE_SHOP",
        record_type="SHOP",
        record_id=str(shop.id),
        details=f"Soft-deleted shop '{shop.shop_name}' ({shop.shop_code})",
        user_id=user_id,
        username=username,
    )
    return True


def get_shops(
    db: Session,
    search: Optional[str] = None,
    status: Optional[str] = None,
    include_deleted: bool = False,
) -> List[OtherShop]:
    """Retrieve partner shops list."""
    query = select(OtherShop)
    if not include_deleted:
        query = query.where(OtherShop.is_deleted == False)
    if status and status != "All":
        query = query.where(OtherShop.status == status)

    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                OtherShop.shop_name.ilike(term),
                OtherShop.shop_code.ilike(term),
                OtherShop.owner_name.ilike(term),
                OtherShop.mobile.ilike(term),
            )
        )

    query = query.order_by(OtherShop.shop_name.asc())
    return list(db.execute(query).scalars().all())


def issue_products_to_shop(
    db: Session,
    shop_id: int,
    items_data: List[Dict[str, Any]],
    issue_date: Optional[date] = None,
    reference_number: Optional[str] = None,
    notes: Optional[str] = None,
    allow_negative_stock: bool = False,
    user_id: Optional[int] = None,
    username: str = "system",
) -> ShopIssue:
    """
    Issue products to another shop.
    Decrements Krishna Colour inventory and records StockTransaction(type='SHOP_ISSUE').
    """
    if not items_data:
        raise ValueError("Must specify at least one product to issue.")

    shop = db.execute(select(OtherShop).where(OtherShop.id == shop_id)).scalar_one_or_none()
    if not shop:
        raise ValueError(f"Shop ID {shop_id} does not exist.")

    count = db.execute(select(func.count(ShopIssue.id))).scalar() or 0
    issue_num = f"ISSUE-{datetime.utcnow().strftime('%Y%m%d')}-{count + 1:04d}"

    issue = ShopIssue(
        issue_number=issue_num,
        shop_id=shop.id,
        issue_date=issue_date or date.today(),
        reference_number=reference_number,
        notes=notes,
        status="PENDING",
        created_by_user_id=user_id,
    )
    db.add(issue)
    db.flush()

    for idx, item in enumerate(items_data, start=1):
        prod_id = item["product_id"]
        product = db.execute(select(Product).where(Product.id == prod_id)).scalar_one_or_none()
        if not product:
            raise ValueError(f"Product ID {prod_id} not found.")

        qty = Decimal(str(item["quantity"]))
        if qty <= Decimal("0.00"):
            raise ValueError("Issue quantity must be greater than zero.")

        if not allow_negative_stock and (product.current_stock - qty) < Decimal("0.00"):
            raise NegativeStockError(
                f"Insufficient stock for '{product.name}'. Current: {product.current_stock} {product.unit}, Issue Requested: {qty} {product.unit}."
            )

        unit_p = Decimal(str(item.get("unit_price", product.selling_price)))

        issue_item = ShopIssueItem(
            issue_id=issue.id,
            product_id=product.id,
            quantity_issued=qty,
            quantity_returned=Decimal("0.00"),
            unit_price=unit_p,
            status="PENDING",
        )
        db.add(issue_item)

        # Decrement product stock
        product.current_stock = product.current_stock - qty
        product.updated_at = datetime.utcnow()

        # Record stock transaction
        stx_code = f"STX-SHOP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{issue.id or 0}-{idx:03d}-{uuid4().hex[:4].upper()}"
        tx = StockTransaction(
            transaction_code=stx_code,
            transaction_type="SHOP_ISSUE",
            product_id=product.id,
            quantity=qty,
            unit_price=unit_p,
            reference_type="SHOP_ISSUE",
            reference_id=issue.issue_number,
            party_name=shop.shop_name,
            notes=f"Issued to {shop.shop_name} ({issue.issue_number})",
            created_by_user_id=user_id,
            is_cancelled=False,
            created_at=datetime.utcnow()
        )
        db.add(tx)

    db.flush()

    log_activity(
        db=db,
        action="SHOP_ISSUE",
        record_type="SHOP",
        record_id=str(issue.id),
        details=f"Issued {len(items_data)} items to shop '{shop.shop_name}'. Issue Ref: {issue.issue_number}",
        user_id=user_id,
        username=username,
    )
    return issue


def record_shop_return(
    db: Session,
    issue_id: int,
    return_items_data: List[Dict[str, Any]],
    return_date: Optional[date] = None,
    condition_notes: Optional[str] = None,
    notes: Optional[str] = None,
    user_id: Optional[int] = None,
    username: str = "system",
) -> ShopReturn:
    """
    Record products returned from another shop.
    Validates returned quantities against remaining pending quantities.
    Increases Krishna Colour inventory and records StockTransaction(type='SHOP_RETURN').
    Updates issue item status and overall issue status.
    """
    issue = db.execute(select(ShopIssue).where(ShopIssue.id == issue_id)).scalar_one_or_none()
    if not issue:
        raise ValueError(f"Shop Issue ID {issue_id} not found.")

    if issue.status == "COMPLETED":
        raise ValueError(f"Issue {issue.issue_number} is already marked as completed.")

    count = db.execute(select(func.count(ShopReturn.id))).scalar() or 0
    ret_num = f"RET-{datetime.utcnow().strftime('%Y%m%d')}-{count + 1:04d}"

    shop_ret = ShopReturn(
        return_number=ret_num,
        shop_id=issue.shop_id,
        issue_id=issue.id,
        return_date=return_date or date.today(),
        condition_notes=condition_notes,
        notes=notes,
        created_by_user_id=user_id,
    )
    db.add(shop_ret)
    db.flush()

    for idx, r_item in enumerate(return_items_data, start=1):
        issue_item_id = r_item["issue_item_id"]
        qty_ret = Decimal(str(r_item["quantity_returned"]))

        if qty_ret <= Decimal("0.00"):
            continue

        item_obj = db.execute(select(ShopIssueItem).where(ShopIssueItem.id == issue_item_id)).scalar_one_or_none()
        if not item_obj or item_obj.issue_id != issue.id:
            raise ValueError(f"Invalid issue item {issue_item_id}.")

        pending_qty = item_obj.quantity_issued - item_obj.quantity_returned
        if qty_ret > pending_qty:
            raise ValueError(
                f"Returned quantity ({qty_ret}) exceeds pending quantity ({pending_qty}) for product '{item_obj.product.name}'."
            )

        ret_item_entry = ShopReturnItem(
            return_id=shop_ret.id,
            issue_item_id=item_obj.id,
            product_id=item_obj.product_id,
            quantity_returned=qty_ret,
            condition_notes=r_item.get("condition_notes", condition_notes),
        )
        db.add(ret_item_entry)

        # Update returned quantity on issue item
        item_obj.quantity_returned = item_obj.quantity_returned + qty_ret
        if item_obj.quantity_returned >= item_obj.quantity_issued:
            item_obj.status = "COMPLETED"
        else:
            item_obj.status = "PARTIALLY_RETURNED"

        # Increase product inventory now that return is confirmed
        product = db.execute(select(Product).where(Product.id == item_obj.product_id)).scalar_one()
        product.current_stock = product.current_stock + qty_ret
        product.updated_at = datetime.utcnow()

        # Record stock movement
        stx_code = f"STX-RET-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{shop_ret.id or 0}-{idx:03d}-{uuid4().hex[:4].upper()}"
        tx = StockTransaction(
            transaction_code=stx_code,
            transaction_type="SHOP_RETURN",
            product_id=product.id,
            quantity=qty_ret,
            unit_price=item_obj.unit_price,
            reference_type="SHOP_RETURN",
            reference_id=shop_ret.return_number,
            party_name=issue.other_shop.shop_name,
            notes=f"Return from {issue.other_shop.shop_name} ({shop_ret.return_number})",
            created_by_user_id=user_id,
            is_cancelled=False,
            created_at=datetime.utcnow()
        )
        db.add(tx)

    # Re-evaluate overall issue status
    all_items = list(db.execute(select(ShopIssueItem).where(ShopIssueItem.issue_id == issue.id)).scalars().all())
    all_completed = all(it.quantity_returned >= it.quantity_issued for it in all_items)
    any_returned = any(it.quantity_returned > Decimal("0.00") for it in all_items)

    if all_completed:
        issue.status = "COMPLETED"
        issue.completed_at = datetime.utcnow()
    elif any_returned:
        issue.status = "PARTIALLY_RETURNED"
    else:
        issue.status = "PENDING"

    issue.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db=db,
        action="SHOP_RETURN",
        record_type="SHOP",
        record_id=str(shop_ret.id),
        details=f"Recorded return {shop_ret.return_number} from shop '{issue.other_shop.shop_name}'. Issue: {issue.issue_number}, Status: {issue.status}",
        user_id=user_id,
        username=username,
    )
    return shop_ret


def mark_issue_as_done(
    db: Session,
    issue_id: int,
    override_incomplete: bool = False,
    override_reason: Optional[str] = None,
    user_id: Optional[int] = None,
    username: str = "system",
) -> ShopIssue:
    """
    Explicit MARK AS DONE action:
    1. Validates that all items have been fully returned (or requires authorized override).
    2. Records completion timestamp.
    3. Sets status to COMPLETED.
    4. Retains transaction permanently in completed return history.
    """
    issue = db.execute(select(ShopIssue).where(ShopIssue.id == issue_id)).scalar_one_or_none()
    if not issue:
        raise ValueError(f"Shop Issue {issue_id} not found.")

    if issue.status == "COMPLETED":
        return issue

    all_items = list(db.execute(select(ShopIssueItem).where(ShopIssueItem.issue_id == issue.id)).scalars().all())
    pending_items = [it for it in all_items if (it.quantity_issued - it.quantity_returned) > Decimal("0.00")]

    if pending_items and not override_incomplete:
        pending_desc = ", ".join(
            f"{it.product.name}: {it.quantity_issued - it.quantity_returned} pending"
            for it in pending_items
        )
        raise IncompleteReturnError(
            f"Cannot mark issue as done. Pending returns exist: {pending_desc}. Use authorized override if items were paid for or written off."
        )

    if pending_items and override_incomplete:
        issue.notes = f"{issue.notes or ''} [FORCE COMPLETED by {username}: {override_reason or 'Authorized override'}]"

    issue.status = "COMPLETED"
    issue.completed_at = datetime.utcnow()
    issue.updated_at = datetime.utcnow()
    db.flush()

    log_activity(
        db=db,
        action="SHOP_ISSUE_DONE",
        record_type="SHOP",
        record_id=str(issue.id),
        details=f"Marked issue {issue.issue_number} for shop '{issue.other_shop.shop_name}' as COMPLETED (Override: {override_incomplete})",
        user_id=user_id,
        username=username,
    )
    return issue


def get_shop_issues(
    db: Session,
    shop_id: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[ShopIssue]:
    """Retrieve shop issue records with filters."""
    query = select(ShopIssue).join(OtherShop, OtherShop.id == ShopIssue.shop_id)

    if shop_id:
        query = query.where(ShopIssue.shop_id == shop_id)
    if status and status != "All":
        query = query.where(ShopIssue.status == status)
    if start_date:
        query = query.where(ShopIssue.issue_date >= start_date)
    if end_date:
        query = query.where(ShopIssue.issue_date <= end_date)

    query = query.order_by(ShopIssue.issue_date.desc(), ShopIssue.id.desc())
    return list(db.execute(query).scalars().all())
