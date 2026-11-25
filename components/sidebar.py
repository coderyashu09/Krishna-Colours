"""
Sidebar navigation component with role-based page visibility and session controls.
"""
import streamlit as st
from config.settings import settings
from auth.login import get_current_user, logout_user
from auth.permissions import is_admin


def render_sidebar() -> str:
    """
    Render clean minimal sidebar navigation.
    Returns the selected page name.
    """
    user = get_current_user() or {"full_name": "Guest", "role": "staff"}
    user_role = user.get("role", "staff")

    with st.sidebar:
        # Shop Brand Info in Sidebar
        st.markdown(
            f"""
            <div style="padding: 10px 0 15px 0; border-bottom: 1px solid #E5E7EB; margin-bottom: 15px;">
                <div style="font-size: 17px; font-weight: 700; color: #172033; letter-spacing: -0.2px;">KRISHNA COLOUR</div>
                <div style="font-size: 11px; font-weight: 600; color: #DC2626; text-transform: uppercase;">Asian Paints</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Primary Navigation List
        pages = [
            "Dashboard",
            "Stock Management",
            "Products",
            "Customers",
            "Billing & Payments",
            "Other Shops",
            "Returns Management",
            "Reports & Analytics",
            "Settings",
        ]

        current = st.session_state.get("current_page", "Dashboard")
        if current not in pages:
            current = "Dashboard"

        selected_page = st.radio(
            "Navigation",
            options=pages,
            index=pages.index(current),
            label_visibility="collapsed",
            key="nav_selection_radio"
        )
        st.session_state.current_page = selected_page

        st.markdown("---")

        # Active User Info
        st.markdown(
            f"""
            <div style="background-color: #F8FAFC; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px; margin-bottom: 12px;">
                <div style="font-size: 11px; color: #64748B; text-transform: uppercase; font-weight: 600;">Signed In As</div>
                <div style="font-size: 13px; font-weight: 700; color: #172033;">{user.get('full_name')}</div>
                <div style="font-size: 11px; color: #2563EB; font-weight: 600;">{'👑 Administrator' if user_role == 'admin' else '👤 Staff Member'}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("🚪 Log Out", use_container_width=True, type="secondary"):
            logout_user()
            st.rerun()

        # Footer Version
        st.markdown(
            """
            <div style="font-size: 10px; color: #94A3B8; text-align: center; margin-top: 20px;">
                Krishna Colour System v1.0<br/>
                Production Edition
            </div>
            """,
            unsafe_allow_html=True
        )

    return selected_page
