"""
Idempotent Initial Seeder for Krishna Colour – Asian Paints Dropdown Items.
Seeds ONLY the initial categories, exact product names, and pack sizes (1 L, 4 L, 10 L, 20 L)
into the database if the item_categories table is empty (so admin deletions/edits persist!).
"""
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from database.models import ItemCategory, ItemProduct, ItemPackSize

INITIAL_CATALOG = {
    "Interior colour": [
        "Tractor emulsion",
        "Tractor spark",
        "Premium emulsion",
        "Royal matt",
        "Royal luxury",
    ],
    "Exterior colour": [
        "Ace",
        "Apex",
        "Ultima",
    ],
    "Exterior primer": [
        "Sparc exterior primer",
        "Exterior wall primer",
        "Damp shith",
        "Damp proof",
    ],
    "Interior primer": [
        "Interior wall primer",
        "St primer",
        "Sprac interior primer",
    ],
}

DEFAULT_PACK_SIZES = ["1 L", "4 L", "10 L", "20 L"]


def seed_initial_dropdown_items(db: Session, force: bool = False) -> dict:
    """
    Seed the initial 4 categories, 15 products, and 4 pack sizes per product.
    If categories already exist and force=False, preserves admin modifications.
    """
    existing_count = db.execute(select(func.count(ItemCategory.id))).scalar() or 0
    if existing_count > 0 and not force:
        return {"seeded": False, "categories": existing_count}

    cats_added = 0
    prods_added = 0
    sizes_added = 0

    for cat_name, prod_list in INITIAL_CATALOG.items():
        cat = db.execute(select(ItemCategory).where(ItemCategory.name == cat_name)).scalar_one_or_none()
        if not cat:
            cat = ItemCategory(name=cat_name, is_active=True)
            db.add(cat)
            db.flush()
            cats_added += 1

        for prod_name in prod_list:
            prod = db.execute(
                select(ItemProduct).where(
                    ItemProduct.category_id == cat.id,
                    ItemProduct.name == prod_name,
                )
            ).scalar_one_or_none()
            if not prod:
                prod = ItemProduct(category_id=cat.id, name=prod_name, is_active=True)
                db.add(prod)
                db.flush()
                prods_added += 1

            for idx, size_label in enumerate(DEFAULT_PACK_SIZES, start=1):
                ps = db.execute(
                    select(ItemPackSize).where(
                        ItemPackSize.product_id == prod.id,
                        ItemPackSize.size_label == size_label,
                    )
                ).scalar_one_or_none()
                if not ps:
                    db.add(
                        ItemPackSize(
                            product_id=prod.id,
                            size_label=size_label,
                            sort_order=idx,
                            is_active=True,
                        )
                    )
                    sizes_added += 1

    db.flush()
    return {
        "seeded": True,
        "categories_added": cats_added,
        "products_added": prods_added,
        "pack_sizes_added": sizes_added,
    }
