"""
Reusable KPI cards, stat widgets, and status pills.
"""
import streamlit as st
from typing import Optional, Union
from decimal import Decimal
from utils.helpers import format_currency


def render_kpi_card(
    label: str,
    value: Union[str, int, float, Decimal],
    subtext: Optional[str] = None,
    color_border: Optional[str] = None,
    is_currency: bool = False,
):
    """Render modern financial KPI metric card."""
    if is_currency:
        val_str = format_currency(value)
    elif isinstance(value, (int, float, Decimal)):
        val_str = f"{value:,}" if isinstance(value, int) else f"{float(value):,.2f}"
    else:
        val_str = str(value)

    border_style = f"border-left: 4px solid {color_border};" if color_border else ""
    subtext_html = f'<div class="kpi-subtext">{subtext}</div>' if subtext else ""

    st.markdown(
        f"""
        <div class="kpi-card" style="{border_style}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{val_str}</div>
            {subtext_html}
        </div>
        """,
        unsafe_allow_html=True
    )


def status_pill_html(status: str) -> str:
    """Generate HTML pill for status rendering."""
    s = status.upper().strip()
    if s in ("PAID", "COMPLETED", "ACTIVE", "SUCCESS"):
        cls = "status-pill-paid"
    elif s in ("PARTIALLY_PAID", "PARTIALLY_RETURNED", "LOW_STOCK"):
        cls = "status-pill-partial"
    elif s in ("PENDING", "OUT_OF_STOCK", "CANCELLED", "FAILED"):
        cls = "status-pill-pending"
    else:
        cls = "status-pill-completed"
    return f'<span class="status-pill {cls}">{status}</span>'
