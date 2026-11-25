"""
Reports & Business Analytics Page.
Provides all 15 operational reports with dynamic date ranges, customer/shop/product filtering,
and instant Excel, CSV, and PDF export capabilities.
"""
from datetime import datetime, date, timedelta
import io
import streamlit as st
import pandas as pd
from sqlalchemy import select

from config.database import get_db
from database.models import Customer, OtherShop, Product
from components.header import render_header
from components.cards import render_kpi_card
from services.report_service import get_report_data
from utils.excel_handler import export_dataframe_to_excel
from utils.helpers import format_currency


REPORT_LIST = [
    "1. Daily Sales Report",
    "2. Weekly Sales Report",
    "3. Monthly Sales Report",
    "4. Annual Sales Report",
    "5. Customer-wise Sales",
    "6. Product-wise Sales",
    "7. Stock-in Report",
    "8. Stock-out Report",
    "9. Current Inventory Report",
    "10. Low-stock Report",
    "11. Customer Pending-payment Report",
    "12. Payment Collection Report",
    "13. Other-shop Transaction Report",
    "14. Pending-return Report",
    "15. Completed-return Report",
]


def render_reports_page():
    """Render Business Reports & Analytics interface."""
    render_header("Reports & Business Analytics")

    col_rep, col_d1, col_d2 = st.columns([2, 1, 1])
    with col_rep:
        selected_report = st.selectbox("Select Report to Generate", options=REPORT_LIST)
    with col_d1:
        default_start = date.today().replace(day=1)
        start_date = st.date_input("Start Date", value=default_start)
    with col_d2:
        end_date = st.date_input("End Date", value=date.today())

    # Dynamic Filter row
    with get_db() as db:
        customers = db.execute(select(Customer).where(Customer.is_deleted == False).order_by(Customer.name.asc())).scalars().all()
        shops = db.execute(select(OtherShop).where(OtherShop.is_deleted == False).order_by(OtherShop.shop_name.asc())).scalars().all()
        products = db.execute(select(Product).where(Product.is_deleted == False).order_by(Product.name.asc())).scalars().all()

    col_fc, col_fs, col_fp = st.columns(3)
    target_cust_id = None
    target_shop_id = None
    target_prod_id = None

    with col_fc:
        cust_opts = ["All Customers"] + [f"{c.name} ({c.customer_code})" for c in customers]
        sel_c = st.selectbox("Customer Filter", options=cust_opts)
        if sel_c != "All Customers":
            found_c = next((c for c in customers if f"{c.name} ({c.customer_code})" == sel_c), None)
            if found_c: target_cust_id = found_c.id

    with col_fs:
        shop_opts = ["All Partner Shops"] + [f"{s.shop_name} ({s.shop_code})" for s in shops]
        sel_s = st.selectbox("Shop Filter", options=shop_opts)
        if sel_s != "All Partner Shops":
            found_s = next((s for s in shops if f"{s.shop_name} ({s.shop_code})" == sel_s), None)
            if found_s: target_shop_id = found_s.id

    with col_fp:
        prod_opts = ["All Products"] + [f"{p.name} ({p.product_code})" for p in products]
        sel_p = st.selectbox("Product Filter", options=prod_opts)
        if sel_p != "All Products":
            found_p = next((p for p in products if f"{p.name} ({p.product_code})" == sel_p), None)
            if found_p: target_prod_id = found_p.id

    st.markdown("---")

    # Generate Report Data
    with get_db() as db:
        df_report = get_report_data(
            db=db,
            report_type=selected_report,
            start_date=start_date,
            end_date=end_date,
            customer_id=target_cust_id,
            shop_id=target_shop_id,
            product_id=target_prod_id,
        )

    # Report Header & Metric Summary
    st.markdown(f"### {selected_report}")
    st.caption(f"Date Range: {start_date.strftime('%d-%b-%Y')} to {end_date.strftime('%d-%b-%Y')} | Total Records: {len(df_report)}")

    if df_report.empty:
        st.info("No records found matching the specified date range and filters.")
    else:
        st.dataframe(df_report, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("##### 📥 Export Report")
        col_ex_excel, col_ex_csv = st.columns(2)

        with col_ex_excel:
            clean_title = f"Krishna Colour - {selected_report}"
            excel_bytes = export_dataframe_to_excel(
                df_report,
                sheet_name="Report",
                title=clean_title
            )
            file_slug = selected_report.split(".")[1].strip().lower().replace(" ", "_")
            st.download_button(
                "📥 Export to Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"krishna_colour_{file_slug}_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )

        with col_ex_csv:
            csv_bytes = df_report.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Export to CSV",
                data=csv_bytes,
                file_name=f"krishna_colour_{file_slug}_{date.today().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
