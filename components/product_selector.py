"""
Dual-Mode Item Entry Component for Krishna Colour – Asian Paints.
Provides ONLY two options per item:
  Option A: Select from Dropdown (Category -> Product -> Pack Size from DB)
  Option B: Custom Item Textbox (Manual product name & optional pack size)
"""
from decimal import Decimal
from typing import Optional, Dict, Any
import streamlit as st
from sqlalchemy.orm import Session

from services.item_service import (
    get_categories,
    get_products_for_category,
    get_pack_sizes_for_product,
)


def render_item_entry_widget(
    db: Session,
    key_prefix: str = "item_entry",
) -> Optional[Dict[str, Any]]:
    """
    Render the two-option item selector (Dropdown OR Custom Item Textbox) + Quantity.
    Returns a prepared item dict when user clicks 'Add Item', or None otherwise.
    """
    entry_choice = st.radio(
        "Item Entry Method",
        options=["Option A: Select from Dropdown", "Option B: Custom Item Textbox"],
        horizontal=True,
        key=f"{key_prefix}_mode",
    )

    if entry_choice == "Option A: Select from Dropdown":
        categories = get_categories(db, include_inactive=False)
        if not categories:
            st.warning("No active categories found in Admin Settings. Use Option B (Custom Item) or add categories.")
            return None

        col_c, col_p, col_s, col_q = st.columns([1.3, 1.5, 1.0, 0.8])
        with col_c:
            cat_map = {c.name: c for c in categories}
            sel_cat_name = st.selectbox(
                "Category",
                options=list(cat_map.keys()),
                key=f"{key_prefix}_cat",
            )
            sel_cat = cat_map[sel_cat_name]

        with col_p:
            products = get_products_for_category(db, sel_cat.id, include_inactive=False)
            if not products:
                st.info("No products in this category.")
                return None
            prod_map = {p.name: p for p in products}
            sel_prod_name = st.selectbox(
                "Product",
                options=list(prod_map.keys()),
                key=f"{key_prefix}_prod",
            )
            sel_prod = prod_map[sel_prod_name]

        with col_s:
            pack_sizes = get_pack_sizes_for_product(db, sel_prod.id, include_inactive=False)
            if pack_sizes:
                ps_map = {ps.size_label: ps for ps in pack_sizes}
                sel_ps_label = st.selectbox(
                    "Pack Size",
                    options=list(ps_map.keys()),
                    key=f"{key_prefix}_ps",
                )
                sel_ps = ps_map[sel_ps_label]
            else:
                sel_ps = None
                sel_ps_label = st.text_input("Pack Size", value="", placeholder="e.g. 1 L", key=f"{key_prefix}_ps_txt")

        with col_q:
            qty = st.number_input(
                "Qty",
                min_value=0.01,
                value=1.00,
                step=1.00,
                format="%.2f",
                key=f"{key_prefix}_qty_a",
            )

        if st.button("➕ Add Item", key=f"{key_prefix}_add_a", type="secondary"):
            return {
                "entry_type": "DROPDOWN",
                "category_id": sel_cat.id,
                "product_id": sel_prod.id,
                "pack_size_id": sel_ps.id if sel_ps else None,
                "category_name": sel_cat.name,
                "product_name": sel_prod.name,
                "pack_size": sel_ps.size_label if sel_ps else (sel_ps_label or None),
                "quantity": Decimal(str(qty)),
            }

    else:
        col_cn, col_cs, col_cq = st.columns([2.2, 1.2, 0.8])
        with col_cn:
            custom_name = st.text_input(
                "Custom Item Name *",
                placeholder="e.g. Wall putty, Brush 4 inch, Thinner, Asian primer...",
                key=f"{key_prefix}_custom_name",
            )
        with col_cs:
            custom_size = st.text_input(
                "Pack Size / Description (Optional)",
                placeholder="e.g. 5 kg, 500 ml, Standard",
                key=f"{key_prefix}_custom_size",
            )
        with col_cq:
            qty_b = st.number_input(
                "Qty",
                min_value=0.01,
                value=1.00,
                step=1.00,
                format="%.2f",
                key=f"{key_prefix}_qty_b",
            )

        if st.button("➕ Add Custom Item", key=f"{key_prefix}_add_b", type="secondary"):
            if not custom_name.strip():
                st.error("Please enter a custom item name.")
                return None
            return {
                "entry_type": "CUSTOM",
                "category_id": None,
                "product_id": None,
                "pack_size_id": None,
                "category_name": "Custom Item",
                "product_name": custom_name.strip(),
                "pack_size": custom_size.strip() or None,
                "quantity": Decimal(str(qty_b)),
            }

    return None
