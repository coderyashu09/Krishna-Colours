"""
Reusable KPI summary cards and payment status badges.
"""
from decimal import Decimal
from typing import Optional, Union
import streamlit as st
from utils.helpers import format_currency


def render_kpi_card(
    label: str,
    value: Union[str, int, float, Decimal],
    subtext: Optional[str] = None,
    color_border: Optional[str] = None,
    is_currency: bool = False,
):
    """Render clean, light-themed summary KPI card."""
    if is_currency:
        val_str = format_currency(value)
    elif isinstance(value, int):
        val_str = f"{value:,}"
    elif isinstance(value, (float, Decimal)):
        val_str = f"{float(value):,.2f}"
    else:
        val_str = str(value)

    border_style = f"border-left: 4px solid {color_border};" if color_border else ""
    subtext_html = f'<div class="kpi-subtext">{subtext}</div>' if subtext else ""

    card_html = (
        f'<div class="kpi-card" style="{border_style}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{val_str}</div>'
        f'{subtext_html}'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


def status_pill_html(status: str) -> str:
    """Generate clean status badge for Paid / Payment Pending."""
    s = (status or "").strip().lower()
    if s == "paid":
        cls = "status-pill-paid"
    elif "pending" in s:
        cls = "status-pill-pending"
    else:
        cls = "status-pill-completed"
    return f'<span class="status-pill {cls}">{status}</span>'
