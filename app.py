"""
Krishna Colour – Asian Paints Customer Management System.
Main Streamlit Application Entry Point.
"""
from pathlib import Path
import streamlit as st

st.set_page_config(
    page_title="Krishna Colour – Customer Management",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

from config.database import init_db
from auth.login import (
    init_session_state,
    check_session_timeout,
    authenticate_user,
    login_user,
)
from auth.permissions import is_admin
from components.sidebar import render_sidebar
from pages.dashboard import render_dashboard_page
from pages.customers import render_customers_page
from pages.add_customer import render_add_customer_page
from pages.settings import render_settings_page


def inject_custom_css():
    """Load and inject minimal light-theme CSS."""
    css_path = Path(__file__).resolve().parent / "assets" / "styles.css"
    if css_path.exists():
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def render_login_screen():
    """Render clean, secure login screen."""
    col_l1, col_l2, col_l3 = st.columns([1, 1.15, 1])

    with col_l2:
        st.markdown(
            """
            <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 28px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.06); margin-top: 48px; margin-bottom: 18px;">
                <div style="text-align: center;">
                    <div style="font-size: 30px; margin-bottom: 4px;">🎨</div>
                    <div style="font-size: 22px; font-weight: 700; color: #172033; letter-spacing: -0.3px;">KRISHNA COLOUR</div>
                    <div style="font-size: 12px; font-weight: 600; color: #DC2626; text-transform: uppercase; margin-top: 2px;">Asian Paints • Customer Management System</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            st.markdown("##### Authorized Sign In")
            username = st.text_input("Username", value="admin", placeholder="Enter username")
            password = st.text_input("Password", type="password", placeholder="Enter password")

            submit_login = st.form_submit_button("🔐 Sign In", type="primary", use_container_width=True)
            if submit_login:
                if not username.strip() or not password:
                    st.error("Please enter both username and password.")
                else:
                    success, message, user_info = authenticate_user(username, password)
                    if success and user_info:
                        login_user(user_info)
                        st.rerun()
                    else:
                        st.error(message)


def main():
    """Application router."""
    init_db()
    inject_custom_css()
    init_session_state()

    if not check_session_timeout():
        st.session_state.authenticated = False

    if not st.session_state.get("authenticated"):
        render_login_screen()
        return

    selected_page = render_sidebar()
    user = st.session_state.get("user") or {}

    if selected_page == "Dashboard":
        render_dashboard_page()
    elif selected_page == "Customers":
        render_customers_page()
    elif selected_page == "Add Customer":
        render_add_customer_page()
    elif selected_page == "Admin Settings":
        if is_admin(user.get("role", "staff")):
            render_settings_page()
        else:
            st.error("Access denied. Administrator privileges required.")
    else:
        render_dashboard_page()


if __name__ == "__main__":
    main()
