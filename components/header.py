"""
Top application header component with Asian Paints branding and active user profile.
"""
from datetime import datetime
import streamlit as st
from config.settings import settings
from auth.login import get_current_user, logout_user


def render_header(page_title: str):
    """Render top branding bar and page breadcrumb."""
    user = get_current_user() or {"full_name": "User", "role": "staff"}
    today_str = datetime.now().strftime("%A, %d %B %Y")

    role_badge = "Administrator" if user.get("role") == "admin" else "Staff Member"

    st.markdown(
        f"""
        <div class="brand-header-card">
            <div>
                <h1 class="brand-title">KRISHNA COLOUR</h1>
                <div class="brand-subtitle">🎨 Asian Paints Authorized Tinting & Retail Center</div>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 13px; font-weight: 600; color: #172033;">{user.get('full_name')}</div>
                <div style="font-size: 11px; color: #64748B;">{role_badge} | {today_str}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
