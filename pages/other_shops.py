"""
Other Shops Management Page.
Registers external partner paint shops and handles issuing products to them.
Tracks stock movement separately from retail sales.
"""
from datetime import datetime, date
from decimal import Decimal
import streamlit as st
import pandas as pd
from sqlalchemy import select

from config.database import get_db
from database.models import OtherShop, ShopIssue, Product
from components.header import render_header
from components.cards import render_kpi_card, status_pill_html
from services.shop_service import (
    create_shop, update_shop, delete_shop, get_shops, issue_products_to_shop, get_shop_issues
)
from services.inventory_service import get_products, NegativeStockError
from auth.login import get_current_user, user_can
from utils.excel_handler import export_dataframe_to_excel
from utils.helpers import format_currency


def render_other_shops_page():
    """Render Other Shops partner directory and product issue interface."""
    render_header("Other Shops Management")
    user = get_current_user() or {"id": 1, "username": "admin", "role": "admin"}
    is_admin = (user.get("role") == "admin")

    tab_shops, tab_add, tab_issue, tab_history = st.tabs([
        "🏪 Partner Shops Directory",
        "➕ Register New Shop",
        "📤 Issue Products to Shop",
        "📜 Issue History",
    ])

    # 1. SHOPS DIRECTORY
    with tab_shops:
        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            search_sh = st.text_input("🔍 Search Shops", placeholder="Shop name, owner name, code, phone...")
        with col_s2:
            status_sh = st.selectbox("Status", options=["All", "active", "inactive"])

        with get_db() as db:
            shops_list = get_shops(db, search=search_sh, status=status_sh)

        if not shops_list:
            st.info("No partner shops registered yet.")
        else:
            sh_data = []
            for s in shops_list:
                sh_data.append({
                    "Code": s.shop_code,
                    "Shop Name": s.shop_name,
                    "Owner": s.owner_name or "-",
                    "Mobile": s.mobile or "-",
                    "Address": s.address or "-",
                    "Status": s.status.capitalize(),
                    "Active Issues": sum(1 for i in s.issues if i.status != "COMPLETED"),
                })
            df_shops = pd.DataFrame(sh_data)
            st.dataframe(df_shops, use_container_width=True, hide_index=True)

            # Export Excel
            excel_shops_bytes = export_dataframe_to_excel(df_shops, sheet_name="Shops", title="Krishna Colour - Partner Shops")
            st.download_button(
                "📥 Export Partner Shops (Excel)",
                data=excel_shops_bytes,
                file_name=f"krishna_colour_partner_shops_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            st.markdown("---")
            st.subheader("Edit or Deactivate Selected Shop")
            shop_map = {f"{s.shop_name} ({s.shop_code})": s.id for s in shops_list}
            chosen_shop_label = st.selectbox("Select Shop", options=list(shop_map.keys()))
            chosen_shop_id = shop_map[chosen_shop_label]

            with get_db() as db:
                chosen_shop = db.execute(select(OtherShop).where(OtherShop.id == chosen_shop_id)).scalar_one()

            with st.expander(f"📝 Edit '{chosen_shop.shop_name}' Details", expanded=False):
                with st.form(f"edit_shop_{chosen_shop.id}"):
                    e_sname = st.text_input("Shop Name", value=chosen_shop.shop_name)
                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        e_owner = st.text_input("Owner Name", value=chosen_shop.owner_name or "")
                    with col_e2:
                        e_smob = st.text_input("Contact Mobile", value=chosen_shop.mobile or "")

                    e_saddr = st.text_input("Address", value=chosen_shop.address or "")
                    e_snotes = st.text_area("Notes", value=chosen_shop.notes or "")
                    e_sstatus = st.selectbox("Status", options=["active", "inactive"], index=0 if chosen_shop.status == "active" else 1)

                    save_shop_btn = st.form_submit_button("💾 Save Shop Changes", type="primary", use_container_width=True)

                if save_shop_btn:
                    try:
                        with get_db() as db:
                            update_shop(
                                db=db,
                                shop_id=chosen_shop.id,
                                shop_name=e_sname,
                                owner_name=e_owner,
                                mobile=e_smob,
                                address=e_saddr,
                                notes=e_snotes,
                                status=e_sstatus,
                                user_id=user.get("id"),
                                username=user.get("username", "admin"),
                            )
                        st.success("Shop details updated!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error updating shop: {str(e)}")

                if is_admin:
                    st.markdown("---")
                    if st.button(f"🗑️ Deactivate / Delete Shop '{chosen_shop.shop_name}'", type="secondary"):
                        try:
                            with get_db() as db:
                                delete_shop(
                                    db=db,
                                    shop_id=chosen_shop.id,
                                    user_id=user.get("id"),
                                    username=user.get("username", "admin"),
                                )
                            st.success("Shop deactivated successfully.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete shop: {str(e)}")

    # 2. REGISTER SHOP
    with tab_add:
        st.subheader("Register Partner Paint Shop")
        st.caption("Add other shops that exchange paints, bases, or tinting products with Krishna Colour.")

        with st.form("add_shop_form", clear_on_submit=True):
            col_ns1, col_ns2 = st.columns([2, 1])
            with col_ns1:
                new_sname = st.text_input("Shop Name *", placeholder="e.g. Mahavir Hardware & Paints")
            with col_ns2:
                new_scode = st.text_input("Shop Code (Optional, leave blank to auto-generate)", placeholder="e.g. SHOP-005")

            col_ns3, col_ns4 = st.columns(2)
            with col_ns3:
                new_owner = st.text_input("Proprietor / Owner Name", placeholder="e.g. Suresh Kumar")
            with col_ns4:
                new_smob = st.text_input("Contact Mobile Number", placeholder="10-digit mobile number")

            new_saddr = st.text_input("Shop Location / Address", placeholder="Market street, town, landmark...")
            new_snotes = st.text_area("Notes / Terms", placeholder="Exchange policies, credit limits, tinting arrangements...")

            submit_new_shop = st.form_submit_button("➕ Register Shop", type="primary", use_container_width=True)

            if submit_new_shop:
                if not new_sname.strip():
                    st.error("Shop name is required.")
                else:
                    try:
                        with get_db() as db:
                            new_sh = create_shop(
                                db=db,
                                shop_name=new_sname,
                                owner_name=new_owner,
                                mobile=new_smob,
                                address=new_saddr,
                                notes=new_snotes,
                                shop_code=new_scode if new_scode.strip() else None,
                                user_id=user.get("id"),
                                username=user.get("username", "admin"),
                            )
                        st.success(f"Partner Shop '{new_sh.shop_name}' ({new_sh.shop_code}) registered successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to register shop: {str(e)}")

    # 3. ISSUE PRODUCTS TO SHOP
    with tab_issue:
        st.subheader("Issue Products to Partner Shop")
        st.caption("Record products leaving Krishna Colour store to another shop. Deducts available stock transactionally.")

        with get_db() as db:
            active_shops = db.execute(select(OtherShop).where(OtherShop.status == "active", OtherShop.is_deleted == False).order_by(OtherShop.shop_name.asc())).scalars().all()
            available_products = get_products(db, include_deleted=False)

        if not active_shops:
            st.warning("⚠️ No active partner shops registered. Please register a shop first.")
        elif not available_products:
            st.warning("⚠️ No products available in catalog.")
        else:
            col_ish1, col_ish2 = st.columns(2)
            with col_ish1:
                target_shop_map = {f"{s.shop_name} ({s.shop_code})": s.id for s in active_shops}
                chosen_target_label = st.selectbox("Select Partner Shop *", options=list(target_shop_map.keys()))
                target_shop_id = target_shop_map[chosen_target_label]
            with col_ish2:
                issue_date_val = st.date_input("Issue Date", value=date.today())

            col_iref, col_inotes = st.columns(2)
            with col_iref:
                issue_ref_no = st.text_input("Reference # / Challan #", placeholder="e.g. DC-101 / Phone Request")
            with col_inotes:
                issue_notes_val = st.text_input("Notes", placeholder="Expected return date, tinting base borrow...")

            st.markdown("##### Products to Issue")
            if "shop_issue_items" not in st.session_state:
                st.session_state.shop_issue_items = []

            col_iprod, col_iqty, col_ibtn = st.columns([3, 1, 1])
            with col_iprod:
                avail_prod_map = {f"{p.name} ({p.product_code}) - Stock: {p.current_stock} {p.unit}": p for p in available_products}
                sel_issue_prod_lbl = st.selectbox("Select Product", options=list(avail_prod_map.keys()), key="issue_prod_select")
                sel_issue_prod = avail_prod_map[sel_issue_prod_lbl]
            with col_iqty:
                issue_qty = st.number_input("Quantity *", min_value=0.01, value=1.00, step=1.0, format="%.2f", key="issue_prod_qty")
            with col_ibtn:
                st.write("")
                st.write("")
                if st.button("➕ Add to Issue List", key="btn_add_issue_line", use_container_width=True):
                    st.session_state.shop_issue_items.append({
                        "product_id": sel_issue_prod.id,
                        "product_name": sel_issue_prod.name,
                        "quantity": Decimal(str(issue_qty)),
                        "unit": sel_issue_prod.unit,
                        "unit_price": sel_issue_prod.selling_price,
                    })
                    st.rerun()

            if st.session_state.shop_issue_items:
                st.markdown("###### Items Ready to Issue:")
                issue_preview_rows = [
                    {
                        "#": idx,
                        "Product Name": it["product_name"],
                        "Quantity Issued": f"{it['quantity']} {it['unit']}",
                        "Rate (₹)": float(it["unit_price"]),
                    }
                    for idx, it in enumerate(st.session_state.shop_issue_items, start=1)
                ]
                st.dataframe(pd.DataFrame(issue_preview_rows), use_container_width=True, hide_index=True)

                if st.button("🗑️ Clear Items", key="btn_clear_issue_items"):
                    st.session_state.shop_issue_items = []
                    st.rerun()

                st.markdown("---")
                allow_neg_shop = False
                if is_admin:
                    allow_neg_shop = st.checkbox("Admin Override: Allow negative stock if item stock is insufficient", value=False, key="shop_neg_override")

                if st.button("🚀 Confirm Issue & Deduct Stock", type="primary", use_container_width=True):
                    try:
                        with get_db() as db:
                            issue_rec = issue_products_to_shop(
                                db=db,
                                shop_id=target_shop_id,
                                items_data=st.session_state.shop_issue_items,
                                issue_date=issue_date_val,
                                reference_number=issue_ref_no,
                                notes=issue_notes_val,
                                allow_negative_stock=allow_neg_shop,
                                user_id=user.get("id"),
                                username=user.get("username", "admin"),
                            )
                        st.session_state.shop_issue_items = []
                        st.success(f"Issue {issue_rec.issue_number} recorded successfully! Stock deducted.")
                        st.rerun()
                    except NegativeStockError as nse:
                        st.error(f"Stock Error: {str(nse)}")
                    except Exception as e:
                        st.error(f"Failed to issue products: {str(e)}")

    # 4. ISSUE HISTORY
    with tab_history:
        st.subheader("Shop Issue History & Tracking")
        st.caption("Complete historical list of products issued to partner shops.")

        with get_db() as db:
            issues = get_shop_issues(db)

        if not issues:
            st.info("No product issues recorded yet.")
        else:
            issue_rows = []
            for issue in issues:
                for it in issue.items:
                    pending_qty = it.quantity_issued - it.quantity_returned
                    issue_rows.append({
                        "Issue #": issue.issue_number,
                        "Shop": issue.other_shop.shop_name,
                        "Date": issue.issue_date.strftime("%Y-%m-%d"),
                        "Product": it.product.name,
                        "Qty Issued": float(it.quantity_issued),
                        "Qty Returned": float(it.quantity_returned),
                        "Pending Qty": float(pending_qty),
                        "Status": issue.status,
                        "Ref": issue.reference_number or "-",
                    })
            df_issues = pd.DataFrame(issue_rows)
            st.dataframe(df_issues, use_container_width=True, hide_index=True)

            excel_issue_bytes = export_dataframe_to_excel(df_issues, sheet_name="Shop Issues", title="Krishna Colour - Shop Issue History")
            st.download_button(
                "📥 Export Issue History (Excel)",
                data=excel_issue_bytes,
                file_name=f"krishna_colour_shop_issues_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
