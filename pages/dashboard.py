"""
Dashboard Page: Executive live business metrics, financial KPIs, analytics charts, and tabular monitors.
All numbers are computed directly from the central database.
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from config.database import get_db
from config.settings import settings
from components.header import render_header
from components.cards import render_kpi_card
from services.report_service import get_dashboard_metrics, get_dashboard_tables, get_chart_data
from utils.helpers import format_currency


def render_dashboard_page():
    """Render comprehensive live dashboard."""
    render_header("Executive Dashboard")

    with get_db() as db:
        metrics = get_dashboard_metrics(db)
        tables = get_dashboard_tables(db)
        charts = get_chart_data(db)

    # 1. SALES & REVENUE SECTION
    st.markdown('<div class="section-title">📊 Sales & Revenue Overview</div>', unsafe_allow_html=True)
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        render_kpi_card("Today's Sales", metrics["sales"]["today"], "Active billing", color_border="#2563EB", is_currency=True)
    with col2:
        render_kpi_card("This Month's Sales", metrics["sales"]["this_month"], "MTD revenue", color_border="#2563EB", is_currency=True)
    with col3:
        render_kpi_card("Total Sales", metrics["sales"]["total"], f"{metrics['sales']['total_bills']} bills generated", color_border="#16A34A", is_currency=True)
    with col4:
        render_kpi_card("Avg Bill Value", metrics["sales"]["avg_bill_value"], "Per invoice", color_border="#64748B", is_currency=True)
    with col5:
        render_kpi_card("Total Bills", metrics["sales"]["total_bills"], "Finalized invoices", color_border="#2563EB")

    # 2. PAYMENT & OUTSTANDING LEDGER
    st.markdown('<div class="section-title">💰 Payment & Outstanding Collections</div>', unsafe_allow_html=True)
    pcol1, pcol2, pcol3, pcol4, pcol5 = st.columns(5)
    with pcol1:
        render_kpi_card("Total Received", metrics["payments"]["total_received"], "Collected funds", color_border="#16A34A", is_currency=True)
    with pcol2:
        render_kpi_card("Total Outstanding", metrics["payments"]["total_outstanding"], "Pending customer dues", color_border="#DC2626", is_currency=True)
    with pcol3:
        render_kpi_card("Overdue (>30 Days)", metrics["payments"]["overdue_payments"], "Aging customer balances", color_border="#D97706", is_currency=True)
    with pcol4:
        render_kpi_card("Partially Paid Bills", metrics["payments"]["partially_paid_bills"], "Pending full payment", color_border="#D97706")
    with pcol5:
        render_kpi_card("Fully Paid Bills", metrics["payments"]["fully_paid_bills"], "Closed invoices", color_border="#16A34A")

    # 3. INVENTORY & STOCK OVERVIEW
    st.markdown('<div class="section-title">📦 Inventory & Stock Valuation</div>', unsafe_allow_html=True)
    icol1, icol2, icol3, icol4, icol5 = st.columns(5)
    with icol1:
        render_kpi_card("Total Products", metrics["inventory"]["total_products"], "Active catalog items", color_border="#2563EB")
    with icol2:
        render_kpi_card("Available Stock", metrics["inventory"]["total_available_stock"], "Total paint units in store", color_border="#16A34A")
    with icol3:
        render_kpi_card("Stock Purchase Value", metrics["inventory"]["purchase_value"], "Cost valuation", color_border="#64748B", is_currency=True)
    with icol4:
        render_kpi_card("Stock Selling Value", metrics["inventory"]["selling_value"], "Retail valuation", color_border="#2563EB", is_currency=True)
    with icol5:
        low_count = metrics["inventory"]["low_stock"] + metrics["inventory"]["out_of_stock"]
        render_kpi_card("Stock Alerts", low_count, f"{metrics['inventory']['out_of_stock']} out of stock", color_border="#DC2626" if low_count > 0 else "#16A34A")

    # 4. CUSTOMERS & OTHER SHOPS
    st.markdown('<div class="section-title">🤝 Customers & Partner Other-Shops</div>', unsafe_allow_html=True)
    ccol1, ccol2, ccol3, ccol4, ccol5 = st.columns(5)
    with ccol1:
        render_kpi_card("Total Customers", metrics["customers"]["total"], "Registered accounts", color_border="#2563EB")
    with ccol2:
        render_kpi_card("New This Month", metrics["customers"]["new_this_month"], "New registrations", color_border="#16A34A")
    with ccol3:
        render_kpi_card("Registered Shops", metrics["other_shops"]["total_shops"], "Partner shops", color_border="#64748B")
    with ccol4:
        render_kpi_card("Units With Other Shops", metrics["other_shops"]["products_with_shops"], "Awaiting return", color_border="#D97706")
    with ccol5:
        render_kpi_card("Pending Returns", metrics["other_shops"]["pending_returns"], "Uncompleted return issues", color_border="#DC2626" if metrics["other_shops"]["pending_returns"] > 0 else "#16A34A")

    st.markdown("---")

    # 5. CHARTS SECTION
    st.markdown('<div class="section-title">📈 Analytics & Trends</div>', unsafe_allow_html=True)
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("Daily Sales Trend (Last 30 Days)")
        daily_df = charts["daily_sales"]
        if not daily_df.empty:
            fig = px.bar(daily_df, x="Date", y="Sales", text_auto=".2s", color_discrete_sequence=["#2563EB"])
            fig.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=320, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No sales recorded in the last 30 days yet.")

    with chart_col2:
        st.subheader("Payment Collections Trend")
        pay_df = charts["daily_payments"]
        if not pay_df.empty:
            fig_pay = px.line(pay_df, x="Date", y="Collected", markers=True, color_discrete_sequence=["#16A34A"])
            fig_pay.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=320, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF")
            st.plotly_chart(fig_pay, use_container_width=True)
        else:
            st.info("No payments recorded in the last 30 days yet.")

    chart_col3, chart_col4 = st.columns(2)
    with chart_col3:
        st.subheader("Top-Selling Products")
        top_df = charts["top_products"]
        if not top_df.empty:
            fig_top = px.bar(top_df, x="Revenue", y="Product", orientation="h", color_discrete_sequence=["#D97706"])
            fig_top.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=320, yaxis=dict(autorange="reversed"), plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF")
            st.plotly_chart(fig_top, use_container_width=True)
        else:
            st.info("Top-selling products will appear once bills are finalized.")

    with chart_col4:
        st.subheader("Collections vs Outstanding Balance")
        rec = float(metrics["payments"]["total_received"])
        out = float(metrics["payments"]["total_outstanding"])
        if rec > 0 or out > 0:
            fig_pie = px.pie(
                names=["Collected Funds", "Pending Outstanding"],
                values=[rec, out],
                color_discrete_sequence=["#16A34A", "#DC2626"],
                hole=0.45
            )
            fig_pie.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=320)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Payment breakdown will appear once transactions are recorded.")

    st.markdown("---")

    # 6. DASHBOARD TABULAR MONITORS
    st.markdown('<div class="section-title">📋 Operational Monitors</div>', unsafe_allow_html=True)
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "⚠️ High Pending Customers",
        "🧾 Recent Bills",
        "📦 Low Stock Alerts",
        "🔄 Pending Other-Shop Returns",
        "💳 Recent Payments",
        "🚚 Recent Stock Movements",
    ])

    with tab1:
        st.caption("Top 10 customers with the highest outstanding dues.")
        if not tables["high_pending"].empty:
            st.dataframe(tables["high_pending"], use_container_width=True, hide_index=True)
        else:
            st.success("No pending customer dues! All customer accounts are clear.")

    with tab2:
        st.caption("Last 10 generated invoices.")
        if not tables["recent_bills"].empty:
            st.dataframe(tables["recent_bills"], use_container_width=True, hide_index=True)
        else:
            st.info("No bills have been finalized yet.")

    with tab3:
        st.caption("Products at or below their configured minimum stock threshold.")
        if not tables["low_stock"].empty:
            st.dataframe(tables["low_stock"], use_container_width=True, hide_index=True)
        else:
            st.success("All inventory items are well-stocked above minimum thresholds.")

    with tab4:
        st.caption("Active issues with other shops awaiting return of products.")
        if not tables["pending_returns"].empty:
            st.dataframe(tables["pending_returns"], use_container_width=True, hide_index=True)
        else:
            st.success("No pending returns from other shops. All issues are fulfilled.")

    with tab5:
        st.caption("Last 10 received customer payments.")
        if not tables["recent_payments"].empty:
            st.dataframe(tables["recent_payments"], use_container_width=True, hide_index=True)
        else:
            st.info("No payment transactions recorded yet.")

    with tab6:
        st.caption("Last 10 stock in/out movement transactions.")
        if not tables["recent_stock"].empty:
            st.dataframe(tables["recent_stock"], use_container_width=True, hide_index=True)
        else:
            st.info("No stock transactions recorded yet.")
