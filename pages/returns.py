"""
Returns Management Dashboard.
Manages products returned by other partner shops with partial return tracking,
inventory restoration, and explicit MARK AS DONE verification.
Completed records are permanently retained in history.
"""
from datetime import datetime, date
from decimal import Decimal
import streamlit as st
import pandas as pd
from sqlalchemy import select

from config.database import get_db
from database.models import OtherShop, ShopIssue, ShopIssueItem, ShopReturn, Product
from components.header import render_header
from components.cards import render_kpi_card, status_pill_html
from services.shop_service import (
    record_shop_return, mark_issue_as_done, get_shop_issues, get_shops, IncompleteReturnError
)
from auth.login import get_current_user, user_can
from utils.excel_handler import export_dataframe_to_excel
from utils.helpers import format_currency


def render_returns_page():
    """Render Returns Management Dashboard."""
    render_header("Returns Management")
    user = get_current_user() or {"id": 1, "username": "admin", "role": "admin"}
    is_admin = (user.get("role") == "admin")

    with get_db() as db:
        all_shops = get_shops(db)
        shop_filter_opts = ["All"] + [s.shop_name for s in all_shops]

    col_flt_shop, col_flt_date = st.columns(2)
    with col_flt_shop:
        sel_shop_filter = st.selectbox("Filter Partner Shop", options=shop_filter_opts)
    with col_flt_date:
        return_start_date = st.date_input("Filter Issues From", value=date.today().replace(day=1))

    # Fetch issues
    with get_db() as db:
        target_shop_id = None
        if sel_shop_filter != "All":
            sh_obj = next((s for s in all_shops if s.shop_name == sel_shop_filter), None)
            if sh_obj:
                target_shop_id = sh_obj.id

        all_issues = get_shop_issues(db, shop_id=target_shop_id, start_date=return_start_date)

    pending_issues = [i for i in all_issues if i.status == "PENDING"]
    partial_issues = [i for i in all_issues if i.status == "PARTIALLY_RETURNED"]
    completed_issues = [i for i in all_issues if i.status == "COMPLETED"]

    # Dashboard KPI Cards
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    with col_k1:
        render_kpi_card("All Issue Transactions", len(all_issues), "Total tracked", color_border="#2563EB")
    with col_k2:
        render_kpi_card("Pending Returns", len(pending_issues), "No returns recorded yet", color_border="#DC2626")
    with col_k3:
        render_kpi_card("Partially Returned", len(partial_issues), "Partial returns active", color_border="#D97706")
    with col_k4:
        render_kpi_card("Completed Returns", len(completed_issues), "Fulfilled & closed", color_border="#16A34A")

    st.markdown("---")

    # Four primary tabs
    tab_all, tab_pending, tab_partial, tab_completed, tab_action = st.tabs([
        "📋 All Returns",
        "⏳ Pending (0% Returned)",
        "🔄 Partially Returned",
        "✅ Completed History",
        "📥 Record Return / Mark Done",
    ])

    def render_issues_table(issue_subset: list, title: str):
        if not issue_subset:
            st.info(f"No {title.lower()} found.")
            return
        rows = []
        for issue in issue_subset:
            for it in issue.items:
                rem = it.quantity_issued - it.quantity_returned
                rows.append({
                    "Issue #": issue.issue_number,
                    "Shop Name": issue.other_shop.shop_name,
                    "Product": it.product.name,
                    "Issued": float(it.quantity_issued),
                    "Returned": float(it.quantity_returned),
                    "Remaining Pending": float(rem),
                    "Issue Date": issue.issue_date.strftime("%Y-%m-%d"),
                    "Completed Date": issue.completed_at.strftime("%Y-%m-%d") if issue.completed_at else "-",
                    "Status": issue.status,
                })
        df_show = pd.DataFrame(rows)
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        exp_bytes = export_dataframe_to_excel(df_show, sheet_name="Returns", title=f"Krishna Colour - {title}")
        st.download_button(
            f"📥 Export {title} (Excel)",
            data=exp_bytes,
            file_name=f"krishna_colour_{title.lower().replace(' ', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_{title}"
        )

    with tab_all:
        render_issues_table(all_issues, "All Return Records")

    with tab_pending:
        render_issues_table(pending_issues, "Pending Returns")

    with tab_partial:
        render_issues_table(partial_issues, "Partially Returned Items")

    with tab_completed:
        render_issues_table(completed_issues, "Completed Returns History")

    # TAB 5: RECORD RETURN & MARK AS DONE
    with tab_action:
        st.subheader("Process Product Return or Finalize Issue")
        st.caption("Receive returned buckets or tools from other shops. Increases available inventory once confirmed.")

        open_issues = [i for i in all_issues if i.status != "COMPLETED"]
        if not open_issues:
            st.success("🎉 All partner shop issues are fully returned and completed!")
        else:
            issue_choice_map = {
                f"{i.issue_number} – {i.other_shop.shop_name} ({i.status}) | Issued: {i.issue_date}": i.id
                for i in open_issues
            }
            chosen_issue_lbl = st.selectbox("Select Active Issue to Process *", options=list(issue_choice_map.keys()))
            target_issue_id = issue_choice_map[chosen_issue_lbl]

            with get_db() as db:
                target_issue = db.execute(select(ShopIssue).where(ShopIssue.id == target_issue_id)).scalar_one()

            col_sub1, col_sub2 = st.columns([3, 2])

            # Left column: Record Return Form
            with col_sub1:
                st.markdown("##### 1. Record Return Quantity")
                st.caption("Supports partial returns. Returned quantity will automatically be added back to store inventory.")

                with st.form(f"form_ret_{target_issue.id}"):
                    ret_date = st.date_input("Return Confirmation Date", value=date.today())
                    cond_notes = st.selectbox("Item Condition", options=["Intact / Undamaged / Original Seal", "Minor Package Wear", "Damaged / Tinted Container", "Other"])

                    st.markdown("###### Items in this Issue:")
                    return_payload = []
                    for idx, item in enumerate(target_issue.items):
                        pending_q = item.quantity_issued - item.quantity_returned
                        st.markdown(f"**{item.product.name}** (Issued: {item.quantity_issued} {item.product.unit} | Already Returned: {item.quantity_returned} | **Pending: {pending_q}**)")

                        if pending_q > Decimal("0.00"):
                            entered_ret = st.number_input(
                                f"Quantity Returned for '{item.product.name}'",
                                min_value=0.00,
                                max_value=float(pending_q),
                                value=float(pending_q),
                                step=1.0,
                                format="%.2f",
                                key=f"ret_qty_{item.id}"
                            )
                            return_payload.append({
                                "issue_item_id": item.id,
                                "quantity_returned": entered_ret,
                                "condition_notes": cond_notes,
                            })

                    notes_ret = st.text_input("General Return Notes", placeholder="e.g. Returned via shop delivery van...")

                    submit_return = st.form_submit_button("📥 Confirm Return & Add to Stock", type="primary", use_container_width=True)

                    if submit_return:
                        valid_items_to_return = [p for p in return_payload if Decimal(str(p["quantity_returned"])) > Decimal("0.00")]
                        if not valid_items_to_return:
                            st.warning("Please enter a return quantity greater than zero.")
                        else:
                            try:
                                with get_db() as db:
                                    ret_obj = record_shop_return(
                                        db=db,
                                        issue_id=target_issue.id,
                                        return_items_data=valid_items_to_return,
                                        return_date=ret_date,
                                        condition_notes=cond_notes,
                                        notes=notes_ret,
                                        user_id=user.get("id"),
                                        username=user.get("username", "admin"),
                                    )
                                st.success(f"Return {ret_obj.return_number} confirmed! Products restored to stock.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to record return: {str(e)}")

            # Right column: MARK AS DONE
            with col_sub2:
                st.markdown("##### 2. Explicit 'MARK AS DONE' Action")
                st.caption("Once all items are accounted for, formally mark the issue transaction as COMPLETED.")

                all_items_done = all((it.quantity_issued - it.quantity_returned) <= Decimal("0.00") for it in target_issue.items)

                if all_items_done:
                    st.success("✅ All issued items have been fully returned. Ready to complete.")
                else:
                    st.warning("⚠️ Pending items remain unreturned. Cannot mark as done without authorized override.")

                force_done = False
                override_text = ""
                if not all_items_done and is_admin:
                    force_done = st.checkbox("Admin Override: Force Mark Done (e.g. Items paid for or written off)", value=False)
                    if force_done:
                        override_text = st.text_input("Reason for Force Completion *", placeholder="e.g. Paid in cash directly, damaged write-off...")

                if st.button("🏁 MARK AS DONE", type="primary" if all_items_done else "secondary", use_container_width=True):
                    try:
                        with get_db() as db:
                            done_issue = mark_issue_as_done(
                                db=db,
                                issue_id=target_issue.id,
                                override_incomplete=force_done,
                                override_reason=override_text,
                                user_id=user.get("id"),
                                username=user.get("username", "admin"),
                            )
                        st.success(f"Issue {done_issue.issue_number} is now marked as COMPLETED and archived in history!")
                        st.rerun()
                    except IncompleteReturnError as ire:
                        st.error(f"Action blocked: {str(ire)}")
                    except Exception as e:
                        st.error(f"Failed to complete issue: {str(e)}")
