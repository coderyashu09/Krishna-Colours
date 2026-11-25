"""
Product Catalog Management Page.
Supports Product CRUD, Excel/CSV Import with rigorous validation & preview,
Export to Excel/CSV, search, multi-factor filtering, and category management.
Zero sample products populated automatically.
"""
from datetime import datetime
from decimal import Decimal
import io
import streamlit as st
import pandas as pd
from sqlalchemy import select

from config.database import get_db
from database.models import Product, Category
from components.header import render_header
from components.cards import render_kpi_card, status_pill_html
from services.inventory_service import (
    create_product, update_product, delete_product, get_products, get_low_stock_alerts
)
from auth.login import get_current_user, user_can
from utils.excel_handler import export_dataframe_to_excel, parse_and_validate_products_import
from utils.helpers import format_currency


def render_products_page():
    """Render full product catalog and management interface."""
    render_header("Product Catalog")
    user = get_current_user() or {"id": 1, "username": "admin", "role": "admin"}
    is_admin = (user.get("role") == "admin")

    # Fetch available categories
    with get_db() as db:
        categories = [c.name for c in db.execute(select(Category).order_by(Category.name.asc())).scalars().all()]
        if not categories:
            categories = ["Interior Wall Paints", "Exterior Wall Paints", "Wood & Metal Finishes", "Waterproofing & Primers"]

    tab_catalog, tab_add, tab_import, tab_export = st.tabs([
        "📋 Products Catalog",
        "➕ Add Product",
        "📥 Excel / CSV Import",
        "📤 Export Catalog",
    ])

    # 1. CATALOG TAB
    with tab_catalog:
        col_search, col_cat, col_stock = st.columns([2, 1, 1])
        with col_search:
            search_query = st.text_input("🔍 Search Catalog", placeholder="Product name, code, description, subcategory...")
        with col_cat:
            cat_filter = st.selectbox("Filter Category", options=["All"] + categories)
        with col_stock:
            stock_filter = st.selectbox(
                "Stock Status",
                options=["ALL", "IN_STOCK", "LOW_STOCK", "OUT_OF_STOCK"],
                format_func=lambda x: {"ALL": "All Stock Levels", "IN_STOCK": "In Stock (> Min)", "LOW_STOCK": "Low Stock (≤ Min)", "OUT_OF_STOCK": "Out of Stock (≤ 0)"}[x]
            )

        with get_db() as db:
            products_list = get_products(
                db,
                search=search_query,
                category=cat_filter,
                stock_status=stock_filter,
                include_deleted=False
            )

        if not products_list:
            st.info("No products found matching the criteria. Add products manually or use the Excel/CSV Import tab.")
        else:
            p_rows = []
            for p in products_list:
                status_label = "Active" if p.status == "active" else "Discontinued"
                if p.current_stock <= 0:
                    stock_desc = f"❌ Out of Stock (0 {p.unit})"
                elif p.current_stock <= p.min_stock_level:
                    stock_desc = f"⚠️ Low ({p.current_stock} / {p.min_stock_level} {p.unit})"
                else:
                    stock_desc = f"✅ Available ({p.current_stock} {p.unit})"

                p_rows.append({
                    "ID": p.id,
                    "Code": p.product_code,
                    "Product Name": p.name,
                    "Brand": p.brand,
                    "Category": p.category,
                    "Unit": p.unit,
                    "Stock": stock_desc,
                    "Purchase (₹)": float(p.purchase_price),
                    "Selling (₹)": float(p.selling_price),
                    "Status": status_label,
                })

            df_products = pd.DataFrame(p_rows)
            st.dataframe(df_products.drop(columns=["ID"]), use_container_width=True, hide_index=True)

            # View/Edit/Delete Selected Product
            st.markdown("---")
            st.subheader("Edit or Manage Selected Product")
            selected_code = st.selectbox(
                "Select Product to View/Edit/Delete",
                options=[p.product_code for p in products_list],
                format_func=lambda code: next((f"{p.product_code} – {p.name} ({p.current_stock} {p.unit})" for p in products_list if p.product_code == code), code)
            )

            selected_prod = next((p for p in products_list if p.product_code == selected_code), None)
            if selected_prod:
                with st.expander(f"📝 Edit '{selected_prod.name}' Details", expanded=False):
                    with st.form(f"edit_prod_{selected_prod.id}"):
                        e_name = st.text_input("Product Name", value=selected_prod.name)
                        col_e1, col_e2, col_e3 = st.columns(3)
                        with col_e1:
                            e_cat = st.selectbox("Category", options=categories, index=categories.index(selected_prod.category) if selected_prod.category in categories else 0)
                        with col_e2:
                            e_brand = st.text_input("Brand", value=selected_prod.brand)
                        with col_e3:
                            e_unit = st.selectbox("Unit", options=["Litre", "KG", "ML", "GM", "Piece", "Bucket", "Can", "Box", "Roll"], index=0)

                        col_ep1, col_ep2, col_ep3 = st.columns(3)
                        with col_ep1:
                            e_pp = st.number_input("Purchase Price (₹)", min_value=0.00, value=float(selected_prod.purchase_price), step=10.0)
                        with col_ep2:
                            e_sp = st.number_input("Selling Price (₹)", min_value=0.00, value=float(selected_prod.selling_price), step=10.0)
                        with col_ep3:
                            e_min = st.number_input("Min Stock Alert Level", min_value=0.00, value=float(selected_prod.min_stock_level), step=1.0)

                        e_desc = st.text_area("Description / Specifications", value=selected_prod.description or "")

                        col_sub, col_del = st.columns([3, 1])
                        with col_sub:
                            save_btn = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)

                    if save_btn:
                        try:
                            with get_db() as db:
                                update_product(
                                    db=db,
                                    product_id=selected_prod.id,
                                    name=e_name,
                                    category=e_cat,
                                    brand=e_brand,
                                    unit=e_unit,
                                    purchase_price=Decimal(str(e_pp)),
                                    selling_price=Decimal(str(e_sp)),
                                    min_stock_level=Decimal(str(e_min)),
                                    description=e_desc,
                                    user_id=user.get("id"),
                                    username=user.get("username", "admin"),
                                )
                            st.success("Product updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error updating product: {str(e)}")

                    # Delete action
                    if is_admin:
                        st.markdown("---")
                        if st.button(f"🗑️ Delete Product '{selected_prod.name}'", type="secondary"):
                            try:
                                with get_db() as db:
                                    delete_product(
                                        db=db,
                                        product_id=selected_prod.id,
                                        user_id=user.get("id"),
                                        username=user.get("username", "admin"),
                                    )
                                st.success(f"Product '{selected_prod.name}' deleted/deactivated successfully.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to delete product: {str(e)}")

    # 2. ADD PRODUCT TAB
    with tab_add:
        st.subheader("Add New Product to Catalog")
        st.caption("Create a new paint, stainer, primer, or accessory.")

        with st.form("add_product_form", clear_on_submit=True):
            col_a1, col_a2 = st.columns([2, 1])
            with col_a1:
                p_name = st.text_input("Product Name *", placeholder="e.g. Apex Ultima Weatherproof Emulsion White")
            with col_a2:
                p_code = st.text_input("Product Code (Optional, Leave blank to auto-generate)", placeholder="e.g. APEX-WHT-20L")

            col_a3, col_a4, col_a5 = st.columns(3)
            with col_a3:
                p_category = st.selectbox("Category *", options=categories)
            with col_a4:
                p_brand = st.text_input("Brand", value="Asian Paints")
            with col_a5:
                p_unit = st.selectbox("Unit of Measure *", options=["Litre", "KG", "ML", "GM", "Piece", "Bucket", "Can", "Box", "Roll"])

            col_a6, col_a7, col_a8, col_a9 = st.columns(4)
            with col_a6:
                p_purchase = st.number_input("Purchase Price (₹) *", min_value=0.00, step=10.0, format="%.2f")
            with col_a7:
                p_selling = st.number_input("Selling Price (₹) *", min_value=0.00, step=10.0, format="%.2f")
            with col_a8:
                p_opening = st.number_input("Initial Opening Stock", min_value=0.00, step=1.0, format="%.2f")
            with col_a9:
                p_min_stock = st.number_input("Min Alert Threshold", min_value=0.00, value=5.00, step=1.0, format="%.2f")

            p_desc = st.text_area("Product Description & Shade / Tinting Notes", placeholder="e.g. 20 Litre bucket, exterior matte finish, anti-algal guarantee...")

            submitted = st.form_submit_button("➕ Create Product", type="primary", use_container_width=True)

            if submitted:
                if not p_name.strip():
                    st.error("Product name is required.")
                else:
                    try:
                        with get_db() as db:
                            new_prod = create_product(
                                db=db,
                                name=p_name,
                                category=p_category,
                                brand=p_brand,
                                unit=p_unit,
                                purchase_price=Decimal(str(p_purchase)),
                                selling_price=Decimal(str(p_selling)),
                                opening_stock=Decimal(str(p_opening)),
                                min_stock_level=Decimal(str(p_min_stock)),
                                product_code=p_code if p_code.strip() else None,
                                description=p_desc,
                                user_id=user.get("id"),
                                username=user.get("username", "admin"),
                            )
                        st.success(f"Product '{new_prod.name}' ({new_prod.product_code}) created successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create product: {str(e)}")

    # 3. EXCEL / CSV IMPORT TAB
    with tab_import:
        st.subheader("Bulk Import Products via Excel or CSV")
        st.caption("Import the actual official product catalog provided by the business owner.")

        # Download Template
        st.markdown("##### 1. Download Standard Import Template")
        template_df = pd.DataFrame([
            {
                "Product Code": "APEX-WHT-20L",
                "Product Name": "Apex Ultima Weatherproof White",
                "Brand": "Asian Paints",
                "Category": "Exterior Wall Paints",
                "Subcategory": "Premium Emulsion",
                "Unit": "Litre",
                "Purchase Price": 4500.00,
                "Selling Price": 5200.00,
                "Opening Stock": 10.00,
                "Min Stock Level": 3.00,
                "Description": "20L Exterior White Bucket"
            },
            {
                "Product Code": "ROYALE-LUX-10L",
                "Product Name": "Royale Luxury Emulsion",
                "Brand": "Asian Paints",
                "Category": "Interior Wall Paints",
                "Subcategory": "Luxury Finish",
                "Unit": "Litre",
                "Purchase Price": 3800.00,
                "Selling Price": 4400.00,
                "Opening Stock": 15.00,
                "Min Stock Level": 5.00,
                "Description": "10L Teflon surface protector"
            }
        ])
        tmpl_bytes = export_dataframe_to_excel(template_df, sheet_name="Product Template", title="Krishna Colour - Product Import Template")
        st.download_button(
            "📥 Download Excel Template",
            data=tmpl_bytes,
            file_name="krishna_colour_product_import_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.markdown("---")
        st.markdown("##### 2. Upload Completed Spreadsheet (.xlsx, .xls, .csv)")
        uploaded_file = st.file_uploader("Choose catalog file", type=["xlsx", "xls", "csv"], key="uploader_prod")

        if uploaded_file is not None:
            file_bytes = uploaded_file.read()
            valid_rows, error_rows = parse_and_validate_products_import(file_bytes, uploaded_file.name)

            col_v, col_e = st.columns(2)
            with col_v:
                st.metric("Valid Rows Ready to Import", len(valid_rows))
            with col_e:
                st.metric("Invalid Rows (Errors)", len(error_rows))

            if error_rows:
                st.error("⚠️ The following rows contain validation errors and will not be imported:")
                st.dataframe(pd.DataFrame(error_rows), use_container_width=True, hide_index=True)

            if valid_rows:
                st.markdown("##### Preview Valid Rows (First 10 items):")
                preview_df = pd.DataFrame(valid_rows[:10])
                st.dataframe(preview_df, use_container_width=True)

                if st.button("🚀 Confirm & Import Valid Products Into Database", type="primary"):
                    imported_count = 0
                    errors_during_commit = []
                    with get_db() as db:
                        for row in valid_rows:
                            try:
                                create_product(
                                    db=db,
                                    name=row["name"],
                                    category=row["category"],
                                    brand=row["brand"],
                                    subcategory=row.get("subcategory"),
                                    description=row.get("description"),
                                    unit=row["unit"],
                                    purchase_price=row["purchase_price"],
                                    selling_price=row["selling_price"],
                                    opening_stock=row["opening_stock"],
                                    min_stock_level=row["min_stock_level"],
                                    product_code=row.get("product_code"),
                                    user_id=user.get("id"),
                                    username=user.get("username", "admin"),
                                )
                                imported_count += 1
                            except Exception as ex:
                                errors_during_commit.append(f"{row['name']}: {str(ex)}")

                    if imported_count > 0:
                        st.success(f"Successfully imported {imported_count} products into Krishna Colour inventory!")
                    if errors_during_commit:
                        st.warning("Some rows could not be saved: " + "; ".join(errors_during_commit))
                    st.rerun()

    # 4. EXPORT TAB
    with tab_export:
        st.subheader("Export Entire Product Catalog")
        st.caption("Export full current inventory catalog to Excel or CSV.")

        with get_db() as db:
            all_prods = get_products(db, include_deleted=False)

        if not all_prods:
            st.info("Catalog is empty.")
        else:
            export_data = [
                {
                    "Product Code": p.product_code,
                    "Product Name": p.name,
                    "Brand": p.brand,
                    "Category": p.category,
                    "Subcategory": p.subcategory or "",
                    "Unit": p.unit,
                    "Current Stock": float(p.current_stock),
                    "Min Stock Level": float(p.min_stock_level),
                    "Purchase Price (₹)": float(p.purchase_price),
                    "Selling Price (₹)": float(p.selling_price),
                    "Stock Valuation (₹)": float(p.current_stock * p.purchase_price),
                    "Status": p.status,
                    "Description": p.description or "",
                }
                for p in all_prods
            ]
            df_exp = pd.DataFrame(export_data)

            col_x1, col_x2 = st.columns(2)
            with col_x1:
                excel_bytes = export_dataframe_to_excel(df_exp, sheet_name="Products", title="Krishna Colour - Asian Paints Product Catalog")
                st.download_button(
                    "📥 Download Catalog (Excel .xlsx)",
                    data=excel_bytes,
                    file_name=f"krishna_colour_products_{date.today().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            with col_x2:
                csv_bytes = df_exp.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Download Catalog (CSV)",
                    data=csv_bytes,
                    file_name=f"krishna_colour_products_{date.today().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
