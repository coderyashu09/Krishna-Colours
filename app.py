"""
Krishna Colour – Asian Paints Shop Management System.
Main Application Entry Point.
"""
from pathlib import Path
import streamlit as st

# Configure page metadata first
st.set_page_config(
    page_title="Krishna Colour – Asian Paints",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

from config.settings import settings
from config.database import init_db
from auth.login import (
    init_session_state, check_session_timeout, authenticate_user,
    login_user, logout_user, get_current_user
)
from components.sidebar import render_sidebar
from pages.dashboard import render_dashboard_page
from pages.stock import render_stock_page
from pages.products import render_products_page
from pages.customers import render_customers_page
from pages.billing import render_billing_page
from pages.other_shops import render_other_shops_page
from pages.returns import render_returns_page
from pages.reports import render_reports_page
from pages.settings import render_settings_page


def inject_custom_css():
    """Load and inject custom CSS."""
    css_path = Path(__file__).resolve().parent / "assets" / "styles.css"
    if css_path.exists():
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)


def render_login_screen():
    """Render modern secure login screen."""
    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])

    with col_l2:
        st.markdown(
            f"""
            <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 30px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.08); margin-top: 40px; margin-bottom: 20px;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <div style="font-size: 32px; margin-bottom: 4px;">🎨</div>
                    <div style="font-size: 22px; font-weight: 700; color: #172033; letter-spacing: -0.3px;">KRISHNA COLOUR</div>
                    <div style="font-size: 13px; font-weight: 600; color: #DC2626; text-transform: uppercase;">Asian Paints Authorized Center</div>
                    <div style="font-size: 12px; color: #64748B; margin-top: 4px;">Inventory & Shop Management System</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.form("login_form", clear_on_submit=False):
            st.markdown("##### Secure Staff & Admin Sign In")
            username = st.text_input("Username", value="admin", placeholder="e.g. admin or staff")
            password = st.text_input("Password", type="password", placeholder="Enter your password")

            submit_login = st.form_submit_button("🔐 Sign In to System", type="primary", use_container_width=True)

            if submit_login:
                if not username.strip() or not password:
                    st.error("Please enter both username and password.")
                else:
                    success, message, user_info = authenticate_user(username, password)
                    if success and user_info:
                        login_user(user_info)
                        st.success("Authentication successful! Redirecting...")
                        st.rerun()
                    else:
                        st.error(message)

        st.markdown(
            """
            <div style="text-align: center; font-size: 11px; color: #94A3B8; margin-top: 15px;">
                Default Administrator Account: <b>admin</b><br/>
                Protected by Argon2/bcrypt Server-Side Authentication
            </div>
            """,
            unsafe_allow_html=True
        )


def main():
    """Application router."""
    # Ensure database is initialized
    init_db()

    # Inject styling
    inject_custom_css()

    # Session State
    init_session_state()

    # Verify session timeout
    if not check_session_timeout():
        st.session_state.authenticated = False

    # Check Authentication
    if not st.session_state.get("authenticated"):
        render_login_screen()
        return

    # Render Sidebar and Route Page
    selected_page = render_sidebar()

    if selected_page == "Dashboard":
        render_dashboard_page()
    elif selected_page == "Stock Management":
        render_stock_page()
    elif selected_page == "Products":
        render_products_page()
    elif selected_page == "Customers":
        render_customers_page()
    elif selected_page == "Billing & Payments":
        render_billing_page()
    elif selected_page == "Other Shops":
        render_other_shops_page()
    elif selected_page == "Returns Management":
        render_returns_page()
    elif selected_page == "Reports & Analytics":
        render_reports_page()
    elif selected_page == "Settings":
        render_settings_page()
    else:
        render_dashboard_page()


if __name__ == "__main__":
    main()
