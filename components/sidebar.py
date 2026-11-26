"""
Minimal Sidebar Navigation Component for Krishna Colour – Asian Paints Customer Management System.
"""
import streamlit as st
from auth.login import get_current_user, logout_user
from auth.permissions import is_admin


def navigate_to(page_name: str):
    """Safely navigate to another page on the next rerun without widget-key conflicts."""
    st.session_state["_pending_nav"] = page_name


def render_sidebar() -> str:
    """Render minimal, clean sidebar navigation and return selected page key."""
    user = get_current_user() or {"full_name": "Guest", "role": "staff"}
    user_role = user.get("role", "staff")

    with st.sidebar:
        st.markdown(
            """
            <div style="padding: 8px 0 14px 0; border-bottom: 1px solid #E5E7EB; margin-bottom: 14px;">
                <div style="font-size: 17px; font-weight: 700; color: #172033; letter-spacing: -0.2px;">KRISHNA COLOUR</div>
                <div style="font-size: 11px; font-weight: 600; color: #DC2626; text-transform: uppercase;">Asian Paints • Customer Manager</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        pages = ["Dashboard", "Customers", "Add Customer"]
        if is_admin(user_role):
            pages.append("Admin Settings")

        page_labels = {
            "Dashboard": "📊  Dashboard",
            "Customers": "👥  Customers",
            "Add Customer": "➕  Add Customer",
            "Admin Settings": "⚙️  Admin Settings",
        }

        if "_pending_nav" in st.session_state:
            target = st.session_state.pop("_pending_nav")
            if target in pages:
                st.session_state.current_page = target
                st.session_state.nav_selection_radio = target

        current = st.session_state.get("current_page", "Dashboard")
        if current not in pages:
            current = "Dashboard"
        if "nav_selection_radio" not in st.session_state or st.session_state.nav_selection_radio not in pages:
            st.session_state.nav_selection_radio = current

        selected_page = st.radio(
            "Navigation",
            options=pages,
            format_func=lambda x: page_labels.get(x, x),
            label_visibility="collapsed",
            key="nav_selection_radio",
        )
        st.session_state.current_page = selected_page

        st.markdown("---")

        st.markdown(
            f"""
            <div style="background-color: #F8FAFC; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px; margin-bottom: 12px;">
                <div style="font-size: 11px; color: #64748B; text-transform: uppercase; font-weight: 600;">Signed In</div>
                <div style="font-size: 13px; font-weight: 700; color: #172033;">{user.get('full_name')}</div>
                <div style="font-size: 11px; color: #2563EB; font-weight: 600;">{'Administrator' if user_role == 'admin' else 'Staff'}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🚪 Log Out", use_container_width=True, type="secondary"):
            logout_user()
            st.rerun()

    return selected_page
