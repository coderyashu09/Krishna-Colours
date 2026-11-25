"""
Customer Management Page: Directory, Profile Summaries, Ledger Statements, and Excel Import/Export.
Supports unlimited bills per customer and soft-deletes to preserve accounting history.
"""
from datetime import datetime, date
from decimal import Decimal
import streamlit as st
import pandas as pd
from sqlalchemy import select

from config.database import get_db
from database.models import Customer, Bill, Payment
from components.header import render_header
from components.cards import render_kpi_card, status_pill_html
from services.customer_service import (
    create_customer, update_customer, delete_customer, get_customers, get_customer_summary
)
from services.payment_service import get_customer_statement
from auth.login import get_current_user, user_can
from utils.excel_handler import export_dataframe_to_excel, parse_and_validate_customers_import
from utils.pdf_generator import generate_customer_statement_pdf
from utils.helpers import format_currency


def render_customers_page():
    """Render customer management interface."""
    render_header("Customer Management")
    user = get_current_user() or {"id": 1, "username": "admin", "role": "admin"}
    is_admin = (user.get("role") == "admin")

    tab_dir, tab_add, tab_ledger, tab_import = st.tabs([
        "👥 Customer Directory",
        "➕ Register Customer",
        "📑 Customer Statement & Ledger",
        "📥 Excel / CSV Import",
    ])

    # 1. DIRECTORY TAB
    with tab_dir:
        col_s, col_status = st.columns([3, 1])
        with col_s:
            search_c = st.text_input("🔍 Search Customers", placeholder="Name, phone number, customer code, city...")
        with col_status:
            status_f = st.selectbox("Status", options=["All", "active", "inactive"])

        with get_db() as db:
            customers_list = get_customers(db, search=search_c, status=status_f)

        if not customers_list:
            st.info("No customers found. Register new customers using the 'Register Customer' tab.")
        else:
            cust_rows = []
            for c in customers_list:
                cust_rows.append({
                    "Code": c.customer_code,
                    "Name": c.name,
                    "Mobile": c.mobile,
                    "Alt Mobile": c.alternate_mobile or "-",
                    "City": c.city or "-",
                    "Status": c.status.capitalize(),
                    "Registered": c.created_at.strftime("%Y-%m-%d"),
                })
            df_cust = pd.DataFrame(cust_rows)
            st.dataframe(df_cust, use_container_width=True, hide_index=True)

            # Export Customers Excel
            exp_bytes = export_dataframe_to_excel(df_cust, sheet_name="Customers", title="Krishna Colour - Customer Directory")
            st.download_button(
                "📥 Export Customer Directory (Excel)",
                data=exp_bytes,
                file_name=f"krishna_colour_customers_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            st.markdown("---")
            # Edit / Delete Section
            st.subheader("Edit or Manage Selected Customer")
            selected_code = st.selectbox(
                "Select Customer to Edit",
                options=[c.customer_code for c in customers_list],
                format_func=lambda code: next((f"{c.customer_code} – {c.name} ({c.mobile})" for c in customers_list if c.customer_code == code), code)
            )

            sel_cust = next((c for c in customers_list if c.customer_code == selected_code), None)
            if sel_cust:
                with st.expander(f"📝 Edit '{sel_cust.name}' Profile", expanded=False):
                    with st.form(f"edit_cust_{sel_cust.id}"):
                        c_name = st.text_input("Customer Name", value=sel_cust.name)
                        col_cm1, col_cm2 = st.columns(2)
                        with col_cm1:
                            c_mob = st.text_input("Primary Mobile Number", value=sel_cust.mobile)
                        with col_cm2:
                            c_alt = st.text_input("Alternate Mobile", value=sel_cust.alternate_mobile or "")

                        col_ca1, col_ca2 = st.columns([2, 1])
                        with col_ca1:
                            c_addr = st.text_input("Full Address", value=sel_cust.address or "")
                        with col_ca2:
                            c_city = st.text_input("City / Area", value=sel_cust.city or "")

                        c_notes = st.text_area("Notes", value=sel_cust.notes or "")
                        c_status = st.selectbox("Status", options=["active", "inactive"], index=0 if sel_cust.status == "active" else 1)

                        save_c = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)

                    if save_c:
                        try:
                            with get_db() as db:
                                update_customer(
                                    db=db,
                                    customer_id=sel_cust.id,
                                    name=c_name,
                                    mobile=c_mob,
                                    alternate_mobile=c_alt,
                                    address=c_addr,
                                    city=c_city,
                                    notes=c_notes,
                                    status=c_status,
                                    user_id=user.get("id"),
                                    username=user.get("username", "admin"),
                                )
                            st.success("Customer profile updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error updating customer: {str(e)}")

                    if is_admin:
                        st.markdown("---")
                        if st.button(f"🗑️ Deactivate / Delete Customer '{sel_cust.name}'", type="secondary"):
                            try:
                                with get_db() as db:
                                    delete_customer(
                                        db=db,
                                        customer_id=sel_cust.id,
                                        user_id=user.get("id"),
                                        username=user.get("username", "admin"),
                                    )
                                st.success("Customer deleted/deactivated successfully.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to delete customer: {str(e)}")

    # 2. REGISTER CUSTOMER TAB
    with tab_add:
        st.subheader("Register New Customer")
        st.caption("Create a permanent customer profile. All future bills and payments will be linked to this account.")

        with st.form("add_customer_form", clear_on_submit=True):
            col_cn1, col_cn2 = st.columns([2, 1])
            with col_cn1:
                nc_name = st.text_input("Customer Name *", placeholder="e.g. Ramesh Patel / Shivam Painters")
            with col_cn2:
                nc_code = st.text_input("Customer ID / Code (Leave blank to auto-generate)", placeholder="e.g. KC-CUST-0010")

            col_cm1, col_cm2 = st.columns(2)
            with col_cm1:
                nc_mob = st.text_input("Mobile Number *", placeholder="10-digit mobile number")
            with col_cm2:
                nc_alt = st.text_input("Alternate Mobile Number", placeholder="Optional second number")

            col_ca1, col_ca2 = st.columns([2, 1])
            with col_ca1:
                nc_addr = st.text_input("Full Address / Site Address", placeholder="Street, colony, landmark...")
            with col_ca2:
                nc_city = st.text_input("City / District", value="Local Area")

            nc_notes = st.text_area("Contractor / Credit Notes", placeholder="Contractor discount terms, preferred shades...")

            submit_nc = st.form_submit_button("➕ Register Customer", type="primary", use_container_width=True)

            if submit_nc:
                if not nc_name.strip() or not nc_mob.strip():
                    st.error("Customer name and mobile number are required.")
                else:
                    try:
                        with get_db() as db:
                            new_c = create_customer(
                                db=db,
                                name=nc_name,
                                mobile=nc_mob,
                                alternate_mobile=nc_alt,
                                address=nc_addr,
                                city=nc_city,
                                notes=nc_notes,
                                customer_code=nc_code if nc_code.strip() else None,
                                user_id=user.get("id"),
                                username=user.get("username", "admin"),
                            )
                        st.success(f"Customer '{new_c.name}' registered successfully with ID: {new_c.customer_code}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to register customer: {str(e)}")

    # 3. CUSTOMER STATEMENT & LEDGER TAB
    with tab_ledger:
        st.subheader("Customer Detailed Financial Ledger & History")
        st.caption("Displays all historical bills (unlimited per customer), payment transactions, and net outstanding balances.")

        with get_db() as db:
            all_customers = get_customers(db)

        if not all_customers:
            st.info("No customers registered yet.")
        else:
            cust_map = {f"{c.name} ({c.customer_code}) – {c.mobile}": c.id for c in all_customers}
            chosen_cust_label = st.selectbox("Select Customer to View Ledger", options=list(cust_map.keys()))
            chosen_cust_id = cust_map[chosen_cust_label]

            with get_db() as db:
                summary = get_customer_summary(db, chosen_cust_id)
                statement = get_customer_statement(db, chosen_cust_id)

            c_obj = summary["customer"]

            # Financial Summary Metrics Cards
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                render_kpi_card("Total Purchases", summary["total_purchase"], f"{len(summary['bills'])} bills", color_border="#2563EB", is_currency=True)
            with col_m2:
                render_kpi_card("Total Paid", summary["total_paid"], f"{len(summary['payments'])} receipts", color_border="#16A34A", is_currency=True)
            with col_m3:
                render_kpi_card("Outstanding Due", summary["outstanding_balance"], "Net pending", color_border="#DC2626" if summary["outstanding_balance"] > 0 else "#16A34A", is_currency=True)
            with col_m4:
                render_kpi_card("Pending Bills", summary["pending_bills_count"], "Unsettled invoices", color_border="#D97706" if summary["pending_bills_count"] > 0 else "#16A34A")

            # PDF and Excel Statement Download
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                pdf_statement = generate_customer_statement_pdf(statement)
                st.download_button(
                    "📄 Download Ledger Statement (PDF)",
                    data=pdf_statement,
                    file_name=f"statement_{c_obj.customer_code}_{date.today().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            with col_dl2:
                df_ledger = pd.DataFrame(statement["ledger"])
                if not df_ledger.empty:
                    excel_statement = export_dataframe_to_excel(
                        df_ledger, sheet_name="Statement",
                        title=f"Krishna Colour - Customer Ledger Statement ({c_obj.name})"
                    )
                    st.download_button(
                        "📥 Download Ledger Statement (Excel)",
                        data=excel_statement,
                        file_name=f"statement_{c_obj.customer_code}_{date.today().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

            # Sub-tabs for Bills, Payments, and Products Bought
            subtab_bills, subtab_payments, subtab_products = st.tabs([
                "🧾 All Associated Bills",
                "💳 Payment History",
                "🎨 Products Purchased",
            ])

            with subtab_bills:
                if not summary["bills"]:
                    st.info("No bills recorded for this customer.")
                else:
                    bills_data = [
                        {
                            "Bill #": b.bill_number,
                            "Date": b.bill_date.strftime("%Y-%m-%d"),
                            "Items Count": len(b.items),
                            "Grand Total (₹)": float(b.grand_total),
                            "Received (₹)": float(b.amount_received),
                            "Outstanding (₹)": float(b.outstanding_amount),
                            "Payment Status": b.payment_status,
                            "Status": b.bill_status,
                        }
                        for b in summary["bills"]
                    ]
                    st.dataframe(pd.DataFrame(bills_data), use_container_width=True, hide_index=True)

            with subtab_payments:
                if not summary["payments"]:
                    st.info("No payment transactions recorded for this customer.")
                else:
                    pay_data = [
                        {
                            "Receipt #": p.payment_number,
                            "Date": p.payment_date.strftime("%Y-%m-%d"),
                            "Amount (₹)": float(p.amount),
                            "Method": p.payment_method,
                            "Bill #": p.bill.bill_number if p.bill else "On Account",
                            "Ref": p.transaction_reference or "-",
                            "Notes": p.notes or "-",
                        }
                        for p in summary["payments"]
                    ]
                    st.dataframe(pd.DataFrame(pay_data), use_container_width=True, hide_index=True)

            with subtab_products:
                if not summary["products_bought"]:
                    st.info("No products purchased yet.")
                else:
                    st.dataframe(pd.DataFrame(summary["products_bought"]), use_container_width=True, hide_index=True)

    # 4. IMPORT TAB
    with tab_import:
        st.subheader("Bulk Import Customers (Excel or CSV)")
        st.caption("Import existing customer directories or contractor contact lists.")

        template_cust = pd.DataFrame([
            {
                "Customer Code": "KC-CUST-0001",
                "Customer Name": "Ramesh Patel",
                "Mobile": "9876543210",
                "Alternate Mobile": "9123456780",
                "Address": "Near Civil Hospital Road",
                "City": "Market Area",
                "Notes": "Prime contractor for Asian Paints Apex"
            }
        ])
        tmpl_c_bytes = export_dataframe_to_excel(template_cust, sheet_name="Customer Template", title="Customer Import Template")
        st.download_button(
            "📥 Download Customer Excel Template",
            data=tmpl_c_bytes,
            file_name="krishna_colour_customer_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.markdown("---")
        c_file = st.file_uploader("Upload Customer List (.xlsx, .xls, .csv)", type=["xlsx", "xls", "csv"], key="uploader_cust")
        if c_file is not None:
            c_bytes = c_file.read()
            valid_c, error_c = parse_and_validate_customers_import(c_bytes, c_file.name)

            col_vc, col_ec = st.columns(2)
            with col_vc:
                st.metric("Valid Customer Records", len(valid_c))
            with col_ec:
                st.metric("Invalid Records (Errors)", len(error_c))

            if error_c:
                st.error("Validation issues found in uploaded records:")
                st.dataframe(pd.DataFrame(error_c), use_container_width=True, hide_index=True)

            if valid_c:
                st.dataframe(pd.DataFrame(valid_c[:10]), use_container_width=True)
                if st.button("🚀 Import Valid Customers", type="primary"):
                    success_c = 0
                    with get_db() as db:
                        for row in valid_c:
                            try:
                                create_customer(
                                    db=db,
                                    name=row["name"],
                                    mobile=row["mobile"],
                                    alternate_mobile=row.get("alternate_mobile"),
                                    address=row.get("address"),
                                    city=row.get("city"),
                                    notes=row.get("notes"),
                                    customer_code=row.get("customer_code"),
                                    user_id=user.get("id"),
                                    username=user.get("username", "admin"),
                                )
                                success_c += 1
                            except Exception:
                                pass
                    st.success(f"Imported {success_c} customers into Krishna Colour database!")
                    st.rerun()
