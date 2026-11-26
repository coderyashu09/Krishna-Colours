"""
Minimal Executive Dashboard for Krishna Colour – Asian Paints Customer Management System.
Shows ONLY:
1. Top Summary (3 cards): Year Amount, Month Amount, Active Customers
2. Payment Pending Customers table with search and click-to-open customer profile.
"""
from decimal import Decimal
import pandas as pd
import streamlit as st

from config.database import get_db
from components.header import render_header
from components.cards import render_kpi_card
from components.sidebar import navigate_to
from services.customer_service import get_dashboard_data
from utils.helpers import format_currency


def render_dashboard_page():
    """Render minimal light-themed dashboard."""
    render_header("Dashboard")

    col_title, col_search = st.columns([2, 1.5])
    with col_title:
        st.markdown('<div class="section-title">Business Overview</div>', unsafe_allow_html=True)
    with col_search:
        pending_search = st.text_input(
            "Search Pending Customers",
            placeholder="Search by customer name, mobile, address, or bill #...",
            label_visibility="collapsed",
            key="dash_pending_search",
        )

    with get_db() as db:
        data = get_dashboard_data(db, pending_search=pending_search)

    # 1. TOP SUMMARY: ONLY THREE CARDS
    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi_card(
            "Year Amount",
            data["year_amount"],
            "Final deal total for current calendar year",
            color_border="#2563EB",
            is_currency=True,
        )
    with c2:
        render_kpi_card(
            "Month Amount",
            data["month_amount"],
            "Final deal total for current month",
            color_border="#16A34A",
            is_currency=True,
        )
    with c3:
        render_kpi_card(
            "Active Customers",
            data["active_customers"],
            "Total active customer records",
            color_border="#172033",
            is_currency=False,
        )

    st.markdown("---")

    # 2. PAYMENT PENDING CUSTOMERS TABLE
    st.markdown('<div class="section-title">Payment Pending Customers</div>', unsafe_allow_html=True)

    pending_bills = data["pending_bills"]
    if not pending_bills:
        if pending_search:
            st.info("No payment pending records match your search.")
        else:
            st.success("All customer bills are fully paid. No pending payments right now.")
        return

    rows = []
    bill_meta = []
    for b in pending_bills:
        cust = b.customer
        rows.append({
            "Customer Name": cust.name,
            "Mobile Number": cust.mobile,
            "Address": cust.address or "—",
            "Bill Number(s)": b.bill_number,
            "Final Deal Amount": format_currency(b.final_deal_amount),
            "Amount Received": format_currency(b.amount_received),
            "Pending Amount": format_currency(b.pending_amount),
            "Bill Date": b.bill_date.strftime("%d-%b-%Y"),
            "Payment Status": b.payment_status,
        })
        bill_meta.append((cust.id, cust.name, cust.customer_code, b.bill_number, b.pending_amount))

    df_pending = pd.DataFrame(rows)

    st.caption("Click any row below (or select from the quick picker) to open that customer's full profile and payment details.")
    selection = st.dataframe(
        df_pending,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="dash_pending_table",
    )

    selected_rows = selection.selection.rows if selection and hasattr(selection, "selection") else []
    if selected_rows:
        idx = selected_rows[0]
        if 0 <= idx < len(bill_meta):
            st.session_state.selected_customer_id = bill_meta[idx][0]
            navigate_to("Customers")
            st.rerun()

    # Mobile-friendly fallback picker
    col_pick, col_btn = st.columns([3, 1])
    with col_pick:
        opts = {
            f"{m[1]} ({m[2]}) — Bill #{m[3]} | Pending: {format_currency(m[4])}": m[0]
            for m in bill_meta
        }
        chosen_lbl = st.selectbox(
            "Open Customer Profile",
            options=list(opts.keys()),
            label_visibility="collapsed",
            key="dash_quick_open_sel",
        )
    with col_btn:
        if st.button("Open Profile →", type="primary", use_container_width=True, key="dash_quick_open_btn"):
            st.session_state.selected_customer_id = opts[chosen_lbl]
            navigate_to("Customers")
            st.rerun()
