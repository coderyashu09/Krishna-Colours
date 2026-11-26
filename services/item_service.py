"""
Admin Dropdown Item Management Service for Krishna Colour – Asian Paints.
Manages Categories, Products, and Pack Sizes stored in the database.
Preserves historical customer bill records by archiving/deactivating used items
instead of hard-deleting them.
"""
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from database.models import ItemCategory, ItemProduct, ItemPackSize, BillItem
from database.seed_asian_paints import DEFAULT_PACK_SIZES
from services.audit_service import log_activity


def get_categories(db: Session, include_inactive: bool = False) -> List[ItemCategory]:
    """Return categories sorted by creation order."""
    q = select(ItemCategory)
    if not include_inactive:
        q = q.where(ItemCategory.is_active == True)
    q = q.order_by(ItemCategory.id.asc())
    return list(db.execute(q).scalars().all())


def get_products_for_category(
    db: Session,
    category_id: int,
    include_inactive: bool = False,
) -> List[ItemProduct]:
    """Return products under a category."""
    q = select(ItemProduct).where(ItemProduct.category_id == category_id)
    if not include_inactive:
        q = q.where(ItemProduct.is_active == True)
    q = q.order_by(ItemProduct.id.asc())
    return list(db.execute(q).scalars().all())


def get_pack_sizes_for_product(
    db: Session,
    product_id: int,
    include_inactive: bool = False,
) -> List[ItemPackSize]:
    """Return pack sizes under a product."""
    q = select(ItemPackSize).where(ItemPackSize.product_id == product_id)
    if not include_inactive:
        q = q.where(ItemPackSize.is_active == True)
    q = q.order_by(ItemPackSize.sort_order.asc(), ItemPackSize.id.asc())
    return list(db.execute(q).scalars().all())


def add_category(db: Session, name: str, username: str = "admin") -> ItemCategory:
    """Create a new category or reactivate if an identical inactive one exists."""
    clean = (name or "").strip()
    if not clean:
        raise ValueError("Category name is required.")

    existing = db.execute(
        select(ItemCategory).where(func.lower(ItemCategory.name) == clean.lower())
    ).scalar_one_or_none()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.name = clean
            existing.updated_at = datetime.utcnow()
            db.flush()
            return existing
        raise ValueError(f"Category '{clean}' already exists.")

    cat = ItemCategory(name=clean, is_active=True)
    db.add(cat)
    db.flush()
    log_activity(db, "ADD_CATEGORY", "ITEM_CATEGORY", str(cat.id), f"Added category '{clean}'", username=username)
    return cat


def rename_category(db: Session, category_id: int, new_name: str, username: str = "admin") -> ItemCategory:
    """Rename an existing category."""
    clean = (new_name or "").strip()
    if not clean:
        raise ValueError("Category name cannot be empty.")
    cat = db.execute(select(ItemCategory).where(ItemCategory.id == category_id)).scalar_one_or_none()
    if not cat:
        raise ValueError("Category not found.")

    dup = db.execute(
        select(ItemCategory).where(
            func.lower(ItemCategory.name) == clean.lower(),
            ItemCategory.id != category_id,
        )
    ).scalar_one_or_none()
    if dup:
        raise ValueError(f"Another category named '{clean}' already exists.")

    old_name = cat.name
    cat.name = clean
    cat.updated_at = datetime.utcnow()
    db.flush()
    log_activity(db, "RENAME_CATEGORY", "ITEM_CATEGORY", str(cat.id), f"Renamed '{old_name}' -> '{clean}'", username=username)
    return cat


def is_category_used_in_bills(db: Session, category_id: int) -> int:
    """Count how many bill items reference this category or its products."""
    cat_refs = db.execute(
        select(func.count(BillItem.id)).where(BillItem.category_id == category_id)
    ).scalar() or 0
    prod_ids = [
        p.id for p in db.execute(select(ItemProduct).where(ItemProduct.category_id == category_id)).scalars().all()
    ]
    if prod_ids:
        prod_refs = db.execute(
            select(func.count(BillItem.id)).where(BillItem.product_id.in_(prod_ids))
        ).scalar() or 0
    else:
        prod_refs = 0
    return max(cat_refs, prod_refs)


def delete_or_archive_category(
    db: Session,
    category_id: int,
    archive_if_used: bool = True,
    username: str = "admin",
) -> Tuple[str, str]:
    """
    Delete an unused category permanently, or archive/deactivate it if already used
    in customer bill records so historical snapshots remain intact.
    Returns (action_taken, message).
    """
    cat = db.execute(select(ItemCategory).where(ItemCategory.id == category_id)).scalar_one_or_none()
    if not cat:
        raise ValueError("Category not found.")

    used_count = is_category_used_in_bills(db, category_id)
    if used_count > 0:
        if not archive_if_used:
            raise ValueError(
                f"Category '{cat.name}' is used in {used_count} historical bill item(s). Confirm archive instead."
            )
        cat.is_active = False
        for p in cat.products:
            p.is_active = False
        db.flush()
        log_activity(db, "ARCHIVE_CATEGORY", "ITEM_CATEGORY", str(cat.id), f"Archived category '{cat.name}'", username=username)
        return "archived", f"Category '{cat.name}' was deactivated (used in {used_count} customer record(s); history preserved)."

    cat_name = cat.name
    db.delete(cat)
    db.flush()
    log_activity(db, "DELETE_CATEGORY", "ITEM_CATEGORY", str(category_id), f"Deleted unused category '{cat_name}'", username=username)
    return "deleted", f"Category '{cat_name}' deleted permanently."


def add_product(
    db: Session,
    category_id: int,
    name: str,
    pack_sizes: Optional[List[str]] = None,
    username: str = "admin",
) -> ItemProduct:
    """Add a product under a category along with pack sizes."""
    clean = (name or "").strip()
    if not clean:
        raise ValueError("Product name is required.")

    cat = db.execute(select(ItemCategory).where(ItemCategory.id == category_id)).scalar_one_or_none()
    if not cat:
        raise ValueError("Selected category does not exist.")

    existing = db.execute(
        select(ItemProduct).where(
            ItemProduct.category_id == category_id,
            func.lower(ItemProduct.name) == clean.lower(),
        )
    ).scalar_one_or_none()

    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.name = clean
            existing.updated_at = datetime.utcnow()
            db.flush()
            return existing
        raise ValueError(f"Product '{clean}' already exists in '{cat.name}'.")

    prod = ItemProduct(category_id=category_id, name=clean, is_active=True)
    db.add(prod)
    db.flush()

    sizes = pack_sizes if pack_sizes else DEFAULT_PACK_SIZES
    seen = set()
    for idx, sz in enumerate(sizes, start=1):
        sz_clean = str(sz).strip()
        if sz_clean and sz_clean.lower() not in seen:
            seen.add(sz_clean.lower())
            db.add(ItemPackSize(product_id=prod.id, size_label=sz_clean, sort_order=idx, is_active=True))

    db.flush()
    log_activity(db, "ADD_PRODUCT", "ITEM_PRODUCT", str(prod.id), f"Added '{clean}' under '{cat.name}'", username=username)
    return prod


def rename_product(db: Session, product_id: int, new_name: str, username: str = "admin") -> ItemProduct:
    """Edit product name cleanly without altering historical bill item snapshots."""
    clean = (new_name or "").strip()
    if not clean:
        raise ValueError("Product name cannot be empty.")

    prod = db.execute(select(ItemProduct).where(ItemProduct.id == product_id)).scalar_one_or_none()
    if not prod:
        raise ValueError("Product not found.")

    dup = db.execute(
        select(ItemProduct).where(
            ItemProduct.category_id == prod.category_id,
            func.lower(ItemProduct.name) == clean.lower(),
            ItemProduct.id != product_id,
        )
    ).scalar_one_or_none()
    if dup:
        raise ValueError(f"Product '{clean}' already exists in this category.")

    old_name = prod.name
    prod.name = clean
    prod.updated_at = datetime.utcnow()
    db.flush()
    log_activity(db, "RENAME_PRODUCT", "ITEM_PRODUCT", str(prod.id), f"Renamed '{old_name}' -> '{clean}'", username=username)
    return prod


def is_product_used_in_bills(db: Session, product_id: int) -> int:
    """Count historical bill items referencing this product."""
    return db.execute(
        select(func.count(BillItem.id)).where(BillItem.product_id == product_id)
    ).scalar() or 0


def remove_or_archive_product(
    db: Session,
    product_id: int,
    archive_only: bool = False,
    username: str = "admin",
) -> Tuple[str, str]:
    """
    Archive/deactivate a product if used in customer bills (or if archive_only=True),
    preserving all historical customer records. Permanently deletes only if unused and archive_only=False.
    """
    prod = db.execute(select(ItemProduct).where(ItemProduct.id == product_id)).scalar_one_or_none()
    if not prod:
        raise ValueError("Product not found.")

    used_count = is_product_used_in_bills(db, product_id)
    if used_count > 0 or archive_only:
        prod.is_active = False
        prod.updated_at = datetime.utcnow()
        db.flush()
        log_activity(
            db, "ARCHIVE_PRODUCT", "ITEM_PRODUCT", str(prod.id),
            f"Deactivated product '{prod.name}' (used in {used_count} bills)", username=username
        )
        msg = f"Product '{prod.name}' deactivated and removed from dropdown."
        if used_count > 0:
            msg += f" Historical records ({used_count} item entries) are preserved."
        return "archived", msg

    prod_name = prod.name
    db.delete(prod)
    db.flush()
    log_activity(db, "DELETE_PRODUCT", "ITEM_PRODUCT", str(product_id), f"Deleted unused product '{prod_name}'", username=username)
    return "deleted", f"Product '{prod_name}' removed permanently."


def reactivate_product(db: Session, product_id: int, username: str = "admin") -> ItemProduct:
    """Restore an archived product back to the active dropdown."""
    prod = db.execute(select(ItemProduct).where(ItemProduct.id == product_id)).scalar_one_or_none()
    if not prod:
        raise ValueError("Product not found.")
    prod.is_active = True
    if prod.category and not prod.category.is_active:
        prod.category.is_active = True
    prod.updated_at = datetime.utcnow()
    db.flush()
    log_activity(db, "REACTIVATE_PRODUCT", "ITEM_PRODUCT", str(prod.id), f"Reactivated '{prod.name}'", username=username)
    return prod


def add_pack_size(db: Session, product_id: int, size_label: str, username: str = "admin") -> ItemPackSize:
    """Add a new pack size to a product."""
    clean = (size_label or "").strip()
    if not clean:
        raise ValueError("Pack size label is required.")

    existing = db.execute(
        select(ItemPackSize).where(
            ItemPackSize.product_id == product_id,
            func.lower(ItemPackSize.size_label) == clean.lower(),
        )
    ).scalar_one_or_none()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.size_label = clean
            existing.updated_at = datetime.utcnow()
            db.flush()
            return existing
        raise ValueError(f"Pack size '{clean}' already exists for this product.")

    max_order = db.execute(
        select(func.max(ItemPackSize.sort_order)).where(ItemPackSize.product_id == product_id)
    ).scalar() or 0
    ps = ItemPackSize(product_id=product_id, size_label=clean, sort_order=max_order + 1, is_active=True)
    db.add(ps)
    db.flush()
    log_activity(db, "ADD_PACK_SIZE", "ITEM_PACK_SIZE", str(ps.id), f"Added pack size '{clean}'", username=username)
    return ps


def rename_pack_size(db: Session, pack_size_id: int, new_label: str, username: str = "admin") -> ItemPackSize:
    """Edit an existing pack size label."""
    clean = (new_label or "").strip()
    if not clean:
        raise ValueError("Pack size cannot be empty.")

    ps = db.execute(select(ItemPackSize).where(ItemPackSize.id == pack_size_id)).scalar_one_or_none()
    if not ps:
        raise ValueError("Pack size not found.")

    dup = db.execute(
        select(ItemPackSize).where(
            ItemPackSize.product_id == ps.product_id,
            func.lower(ItemPackSize.size_label) == clean.lower(),
            ItemPackSize.id != pack_size_id,
        )
    ).scalar_one_or_none()
    if dup:
        raise ValueError(f"Pack size '{clean}' already exists for this product.")

    old = ps.size_label
    ps.size_label = clean
    ps.updated_at = datetime.utcnow()
    db.flush()
    log_activity(db, "RENAME_PACK_SIZE", "ITEM_PACK_SIZE", str(ps.id), f"Renamed pack size '{old}' -> '{clean}'", username=username)
    return ps


def remove_or_archive_pack_size(db: Session, pack_size_id: int, username: str = "admin") -> Tuple[str, str]:
    """Deactivate a pack size if referenced in bills, else delete permanently."""
    ps = db.execute(select(ItemPackSize).where(ItemPackSize.id == pack_size_id)).scalar_one_or_none()
    if not ps:
        raise ValueError("Pack size not found.")

    used = db.execute(select(func.count(BillItem.id)).where(BillItem.pack_size_id == pack_size_id)).scalar() or 0
    if used > 0:
        ps.is_active = False
        ps.updated_at = datetime.utcnow()
        db.flush()
        return "archived", f"Pack size '{ps.size_label}' deactivated (preserved in {used} historical bills)."

    lbl = ps.size_label
    db.delete(ps)
    db.flush()
    return "deleted", f"Pack size '{lbl}' removed."
