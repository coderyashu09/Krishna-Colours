"""
Customers Directory, Search, Profile View, Multi-Bill Editor, and Partial Payment Collection
for Krishna Colour – Asian Paints Customer Management System.
"""
from datetime import date
from decimal import Decimal
import html
import pandas as pd
import streamlit as st

from config.database import get_db
from components.header import render_header
from components.cards import render_kpi_card, status_pill_html
from components.sidebar import navigate_to
from components.product_selector import render_item_entry_widget
from services.customer_service import (
    search_customers,
    get_customer_by_id,
    update_customer_details,
    add_bill_to_customer,
    update_bill,
    delete_bill,
    record_bill_payment,
    DuplicateCustomerError,
    DuplicateBillNumberError,
    InvalidAmountError,
)
from auth.login import get_current_user
from auth.permissions import is_admin
from utils.helpers import format_currency


def _render_customer_profile(customer_id: int, username: str, admin_user: bool):
    """Render complete customer profile with all bill numbers, items, amounts, and payments."""
    with get_db() as db:
        cust = get_customer_by_id(db, customer_id)
        if not cust:
            st.error("Customer record not found.")
            st.session_state.selected_customer_id = None
            return

        # Snapshot data while session is open
        cust_code = cust.customer_code
        cust_name = cust.name
        cust_mobile = cust.mobile
        cust_address = cust.address or ""
        cust_notes = cust.notes or ""
        cust_active = cust.is_active
        total_deal = cust.total_final_deal_amount
        total_rec = cust.total_amount_received
        total_pend = cust.total_pending_amount
        overall_status = cust.overall_payment_status

        bills_snapshot = []
        for b in cust.bills:
            bills_snapshot.append({
                "id": b.id,
                "bill_number": b.bill_number,
                "bill_date": b.bill_date,
                "final_deal_amount": b.final_deal_amount,
                "effective_final_amount": b.effective_final_amount,
                "amount_received": b.amount_received,
                "has_pending": b.has_pending,
                "pending_amount": b.pending_amount,
                "payment_status": b.payment_status,
                "notes": b.notes or "",
                "items": [
                    {
                        "id": it.id,
                        "entry_type": it.entry_type,
                        "category_id": it.category_id,
                        "product_id": it.product_id,
                        "pack_size_id": it.pack_size_id,
                        "category_name": it.category_name,
                        "product_name": it.product_name,
                        "pack_size": it.pack_size,
                        "quantity": it.quantity,
                        "display_label": it.display_label,
                    }
                    for it in b.items
                ],
                "payments": [
                    {
                        "id": p.id,
                        "amount": p.amount,
                        "payment_date": p.payment_date,
                        "payment_method": p.payment_method,
                        "notes": p.notes or "—",
                        "created_by": p.created_by or "—",
                    }
                    for p in b.payments
                ],
            })

    # Top Back Action
    col_back, col_sp = st.columns([1.2, 4])
    with col_back:
        if st.button("← Back to Customers", key="prof_back_btn", use_container_width=True):
            st.session_state.selected_customer_id = None
            st.rerun()

    # Profile Header Banner
    bill_badges = " ".join(
        f'<span style="display:inline-block;background:#EFF6FF;color:#1D4ED8;border:1px solid #BFDBFE;border-radius:6px;padding:2px 8px;font-size:12px;font-weight:600;margin-right:4px;">#{html.escape(str(b["bill_number"]))}</span>'
        for b in bills_snapshot
    ) or '<span style="color:#64748B;font-size:12px;">No bills recorded yet</span>'

    inactive_badge = " • Inactive" if not cust_active else ""
    notes_html = (
        f'<div style="font-size:12px;color:#64748B;margin-top:4px;">Notes: {html.escape(cust_notes)}</div>'
        if cust_notes else ""
    )
    profile_html = "".join([
        '<div class="content-box">',
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">',
        '<div>',
        f'<div style="font-size:12px;font-weight:700;color:#2563EB;">{html.escape(cust_code)}{inactive_badge}</div>',
        f'<div style="font-size:22px;font-weight:700;color:#172033;margin-top:2px;">{html.escape(cust_name)}</div>',
        f'<div style="font-size:13.5px;color:#475569;margin-top:4px;">📞 {html.escape(cust_mobile)} &nbsp;|&nbsp; 📍 {html.escape(cust_address or "No address")}</div>',
        notes_html,
        f'<div style="margin-top:10px;"><span style="font-size:12px;font-weight:600;color:#475569;margin-right:6px;">Bill Numbers:</span>{bill_badges}</div>',
        '</div>',
        '<div style="text-align:right;">',
        status_pill_html(overall_status),
        f'<div style="font-size:12px;color:#64748B;margin-top:6px;">{len(bills_snapshot)} Bill(s)</div>',
        '</div>',
        '</div>',
        '</div>',
    ])
    st.markdown(profile_html, unsafe_allow_html=True)

    # Customer-level Totals
    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi_card("Final Deal Total", total_deal, "Closed & agreed total", color_border="#2563EB", is_currency=True)
    with c2:
        render_kpi_card("Total Amount Received", total_rec, "Collected across all bills", color_border="#16A34A", is_currency=True)
    with c3:
        if total_pend > Decimal("0.00"):
            render_kpi_card("Pending Amount", total_pend, "Final Deal − Received", color_border="#DC2626", is_currency=True)
        else:
            render_kpi_card("Payment Status", "Paid", "All deals closed", color_border="#16A34A", is_currency=False)

    # Edit Customer Details
    with st.expander("✏️ Edit Customer Details", expanded=False):
        with st.form(f"edit_cust_form_{cust_code}"):
            ec1, ec2 = st.columns(2)
            with ec1:
                e_name = st.text_input("Customer Name *", value=cust_name)
            with ec2:
                e_mob = st.text_input("Mobile Number *", value=cust_mobile)
            e_addr = st.text_area("Full Address", value=cust_address, height=70)
            ec3, ec4 = st.columns([2, 1])
            with ec3:
                e_notes = st.text_input("Notes", value=cust_notes)
            with ec4:
                e_active = st.checkbox("Active Customer", value=cust_active)

            if st.form_submit_button("💾 Save Customer Details", type="primary"):
                try:
                    with get_db() as db:
                        update_customer_details(
                            db=db,
                            customer_id=customer_id,
                            name=e_name,
                            mobile=e_mob,
                            address=e_addr,
                            notes=e_notes,
                            is_active=e_active,
                            username=username,
                        )
                    st.success("Customer details updated!")
                    st.rerun()
                except (DuplicateCustomerError, ValueError) as ve:
                    st.error(str(ve))

    st.markdown('<div class="section-title">Bills & Payment History</div>', unsafe_allow_html=True)

    if not bills_snapshot:
        st.info("No bills recorded for this customer yet. Use 'Add Another Bill Number' below.")

    for b in bills_snapshot:
        is_paid = (b["pending_amount"] == Decimal("0.00"))
        header_status = "✅ Paid" if is_paid else f"⏳ Pending {format_currency(b['pending_amount'])}"
        expander_title = (
            f"Bill #{b['bill_number']}  |  {b['bill_date'].strftime('%d-%b-%Y')}  |  "
            f"Final: {format_currency(b['effective_final_amount'])}  |  {header_status}"
        )

        with st.expander(expander_title, expanded=(not is_paid)):
            # Bill Amount Summary Row
            if is_paid:
                ba1, ba2 = st.columns(2)
                with ba1:
                    st.metric("Final Deal Amount", format_currency(b["final_deal_amount"]))
                with ba2:
                    st.metric("Amount Received", format_currency(b["amount_received"]), delta="Paid (Deal Closed)")
            else:
                ba1, ba2, ba3 = st.columns(3)
                with ba1:
                    st.metric("Final Deal Amount", format_currency(b["final_deal_amount"]))
                with ba2:
                    st.metric("Amount Received", format_currency(b["amount_received"]))
                with ba3:
                    st.metric("Pending Amount", format_currency(b["pending_amount"]), delta="Payment Pending", delta_color="inverse")

            if b["notes"]:
                st.caption(f"Bill Notes: {b['notes']}")

            # Items Table
            st.markdown("**Items Purchased:**")
            if b["items"]:
                it_rows = [
                    {
                        "#": idx,
                        "Type": "Dropdown" if it["entry_type"] == "DROPDOWN" else "Custom",
                        "Category": it["category_name"] or "—",
                        "Product / Item": it["product_name"],
                        "Pack Size": it["pack_size"] or "—",
                        "Qty": float(it["quantity"]),
                    }
                    for idx, it in enumerate(b["items"], start=1)
                ]
                st.dataframe(pd.DataFrame(it_rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No line items listed on this bill.")

            # Partial / Full Payment Form (if pending > 0)
            if not is_paid:
                st.markdown("---")
                st.markdown(f"**💳 Collect Payment for Bill #{b['bill_number']}**")
                with st.form(f"pay_form_{b['id']}", clear_on_submit=True):
                    pc1, pc2, pc3 = st.columns(3)
                    with pc1:
                        p_amt = st.number_input(
                            "Payment Amount (₹) *",
                            min_value=0.01,
                            max_value=float(b["pending_amount"]),
                            value=float(b["pending_amount"]),
                            step=50.0,
                            format="%.2f",
                            key=f"pamt_{b['id']}",
                        )
                    with pc2:
                        p_method = st.selectbox("Method", options=["Cash", "UPI", "Bank Transfer", "Cheque", "Other"], key=f"pmeth_{b['id']}")
                    with pc3:
                        p_dt = st.date_input("Payment Date", value=date.today(), key=f"pdt_{b['id']}")
                    p_note = st.text_input("Payment Notes (Optional)", placeholder="UPI ref / cash received by...", key=f"pnote_{b['id']}")

                    if st.form_submit_button("💰 Record Payment", type="primary"):
                        try:
                            with get_db() as db:
                                record_bill_payment(
                                    db=db,
                                    bill_id=b["id"],
                                    payment_amount=Decimal(str(p_amt)),
                                    payment_date=p_dt,
                                    payment_method=p_method,
                                    notes=p_note,
                                    username=username,
                                )
                            st.success(f"Recorded {format_currency(p_amt)} on Bill #{b['bill_number']}!")
                            st.rerun()
                        except (InvalidAmountError, ValueError) as ve:
                            st.error(str(ve))

            # Payment History for this Bill
            if b["payments"]:
                st.markdown("**Payment History:**")
                ph_rows = [
                    {
                        "Date": p["payment_date"].strftime("%d-%b-%Y"),
                        "Amount": format_currency(p["amount"]),
                        "Method": p["payment_method"],
                        "Notes": p["notes"],
                        "Recorded By": p["created_by"],
                    }
                    for p in b["payments"]
                ]
                st.dataframe(pd.DataFrame(ph_rows), use_container_width=True, hide_index=True)

            # Edit Bill / Remove Bill (Admin / Authorized)
            edit_key = f"edit_bill_items_{b['id']}"
            if edit_key not in st.session_state:
                st.session_state[edit_key] = list(b["items"])

            with st.expander(f"✏️ Edit Bill #{b['bill_number']} Details & Items", expanded=False):
                eb1, eb2 = st.columns(2)
                with eb1:
                    new_bno = st.text_input("Bill Number *", value=b["bill_number"], key=f"eb_no_{b['id']}")
                with eb2:
                    new_bdt = st.date_input("Bill Date *", value=b["bill_date"], key=f"eb_dt_{b['id']}")

                ea1, ea2 = st.columns(2)
                with ea1:
                    new_deal = st.number_input(
                        "Final Deal Amount (₹)",
                        min_value=0.00,
                        value=float(b["final_deal_amount"]),
                        step=50.0,
                        format="%.2f",
                        key=f"eb_deal_{b['id']}",
                    )
                with ea2:
                    new_rec = st.number_input(
                        "Amount Received (₹) *",
                        min_value=0.00,
                        value=float(b["amount_received"]),
                        step=50.0,
                        format="%.2f",
                        key=f"eb_rec_{b['id']}",
                    )
                new_has_pend = st.checkbox(
                    "Add Pending Amount (Optional)",
                    value=bool(b["has_pending"]),
                    key=f"eb_has_pend_{b['id']}",
                )

                new_bnotes = st.text_input("Bill Notes", value=b["notes"], key=f"eb_notes_{b['id']}")

                st.markdown("**Edit Items on This Bill:**")
                with get_db() as db:
                    new_edit_item = render_item_entry_widget(db, key_prefix=f"eb_item_sel_{b['id']}")
                if new_edit_item:
                    st.session_state[edit_key].append(new_edit_item)
                    st.rerun()

                if st.session_state[edit_key]:
                    e_rows = [
                        {
                            "#": idx,
                            "Product": it["product_name"],
                            "Pack Size": it.get("pack_size") or "—",
                            "Qty": float(it["quantity"]),
                        }
                        for idx, it in enumerate(st.session_state[edit_key], start=1)
                    ]
                    st.dataframe(pd.DataFrame(e_rows), use_container_width=True, hide_index=True)

                    erm1, erm2 = st.columns([2, 1])
                    with erm1:
                        erm_idx = st.selectbox(
                            "Item to remove",
                            options=list(range(1, len(st.session_state[edit_key]) + 1)),
                            format_func=lambda i: f"#{i}: {st.session_state[edit_key][i-1]['product_name']}",
                            key=f"eb_rm_sel_{b['id']}",
                        )
                    with erm2:
                        st.write("")
                        if st.button("Remove Item", key=f"eb_rm_btn_{b['id']}", use_container_width=True):
                            st.session_state[edit_key].pop(erm_idx - 1)
                            st.rerun()

                col_eb_save, col_eb_del = st.columns([2, 1])
                with col_eb_save:
                    if st.button("💾 Save Bill Changes", type="primary", key=f"eb_save_btn_{b['id']}", use_container_width=True):
                        try:
                            with get_db() as db:
                                update_bill(
                                    db=db,
                                    bill_id=b["id"],
                                    bill_number=new_bno,
                                    bill_date=new_bdt,
                                    final_deal_amount=Decimal(str(new_deal)),
                                    amount_received=Decimal(str(new_rec)),
                                    has_pending=new_has_pend,
                                    items_data=st.session_state[edit_key],
                                    notes=new_bnotes,
                                    username=username,
                                )
                            del st.session_state[edit_key]
                            st.success(f"Bill #{new_bno} updated successfully!")
                            st.rerun()
                        except (DuplicateBillNumberError, InvalidAmountError, ValueError) as ve:
                            st.error(str(ve))

                with col_eb_del:
                    if admin_user:
                        confirm_del = st.checkbox("Confirm remove bill", key=f"eb_del_chk_{b['id']}")
                        if st.button("🗑️ Delete Bill", type="secondary", key=f"eb_del_btn_{b['id']}", use_container_width=True, disabled=not confirm_del):
                            with get_db() as db:
                                delete_bill(db, b["id"], username=username)
                            if edit_key in st.session_state:
                                del st.session_state[edit_key]
                            st.success(f"Bill #{b['bill_number']} removed.")
                            st.rerun()

    # ADD ANOTHER BILL NUMBER SECTION
    st.markdown("---")
    add_items_key = f"prof_add_bill_items_{customer_id}"
    if add_items_key not in st.session_state:
        st.session_state[add_items_key] = []

    with st.expander(f"➕ Add Another Bill Number to {cust_name}", expanded=False):
        ab1, ab2 = st.columns(2)
        with ab1:
            ab_no = st.text_input("New Bill Number *", placeholder="e.g. 245, 246, 12540", key=f"ab_no_{customer_id}")
        with ab2:
            ab_dt = st.date_input("Bill Date *", value=date.today(), key=f"ab_dt_{customer_id}")

        st.markdown("**Items Purchased:**")
        with get_db() as db:
            ab_added = render_item_entry_widget(db, key_prefix=f"ab_item_{customer_id}")
        if ab_added:
            st.session_state[add_items_key].append(ab_added)
            st.rerun()

        if st.session_state[add_items_key]:
            ab_rows = [
                {
                    "#": idx,
                    "Product / Item": it["product_name"],
                    "Pack Size": it.get("pack_size") or "—",
                    "Qty": float(it["quantity"]),
                }
                for idx, it in enumerate(st.session_state[add_items_key], start=1)
            ]
            st.dataframe(pd.DataFrame(ab_rows), use_container_width=True, hide_index=True)
            if st.button("Clear Items List", key=f"ab_clr_{customer_id}"):
                st.session_state[add_items_key] = []
                st.rerun()

        aba1, aba2 = st.columns(2)
        with aba1:
            ab_deal = st.number_input("Final Deal Amount (₹)", min_value=0.00, value=0.00, step=50.0, format="%.2f", key=f"ab_deal_{customer_id}")
        with aba2:
            ab_rec = st.number_input("Amount Received (₹) *", min_value=0.00, value=0.00, step=50.0, format="%.2f", key=f"ab_rec_{customer_id}")
        ab_has_pend = st.checkbox("Add Pending Amount (Optional)", value=False, key=f"ab_has_pend_{customer_id}")

        ab_notes = st.text_input("Bill Notes (Optional)", key=f"ab_notes_{customer_id}")

        if st.button("💾 Save New Bill", type="primary", use_container_width=True, key=f"ab_save_{customer_id}"):
            try:
                with get_db() as db:
                    add_bill_to_customer(
                        db=db,
                        customer_id=customer_id,
                        bill_number=ab_no,
                        bill_date=ab_dt,
                        final_deal_amount=Decimal(str(ab_deal)),
                        amount_received=Decimal(str(ab_rec)),
                        has_pending=ab_has_pend,
                        items_data=st.session_state[add_items_key],
                        notes=ab_notes,
                        username=username,
                    )
                st.session_state[add_items_key] = []
                st.success(f"Bill #{ab_no.strip()} added to {cust_name}!")
                st.rerun()
            except (DuplicateBillNumberError, InvalidAmountError, ValueError) as ve:
                st.error(str(ve))


def render_customers_page():
    """Render Customer Directory & Search or full Customer Profile."""
    render_header("Customers")
    user = get_current_user() or {"username": "admin", "role": "admin"}
    username = user.get("username", "admin")
    admin_user = is_admin(user.get("role", "staff"))

    selected_cid = st.session_state.get("selected_customer_id")
    if selected_cid:
        _render_customer_profile(selected_cid, username=username, admin_user=admin_user)
        return

    # Search, Filter, and Quick Add Bar
    col_s, col_f, col_add = st.columns([2.2, 1.2, 1])
    with col_s:
        search_q = st.text_input(
            "Search Customers",
            placeholder="Search by Name, Mobile, Customer ID (KC-000001), or Bill Number...",
            label_visibility="collapsed",
            key="cust_list_search",
        )
    with col_f:
        status_flt = st.selectbox(
            "Filter",
            options=["All", "Paid", "Payment Pending"],
            format_func=lambda x: "All Customers" if x == "All" else x,
            label_visibility="collapsed",
            key="cust_list_filter",
        )
    with col_add:
        if st.button("➕ Add Customer", type="primary", use_container_width=True, key="cust_goto_add"):
            navigate_to("Add Customer")
            st.rerun()

    with get_db() as db:
        customers = search_customers(db, search=search_q, status_filter=status_flt)
        cust_rows = []
        cust_meta = []
        for c in customers:
            bill_nos = ", ".join(b.bill_number for b in c.bills) if c.bills else "—"
            pend_tot = c.total_pending_amount
            cust_rows.append({
                "Customer ID": c.customer_code,
                "Customer Name": c.name,
                "Mobile Number": c.mobile,
                "Bill Numbers": bill_nos,
                "Final Deal Amount": format_currency(c.total_final_deal_amount),
                "Amount Received": format_currency(c.total_amount_received),
                "Pending Amount": format_currency(pend_tot) if pend_tot > 0 else "—",
                "Payment Status": c.overall_payment_status,
            })
            cust_meta.append((c.id, c.name, c.customer_code, c.mobile))

    if not cust_rows:
        st.info("No customers found matching your search or filter. Click '➕ Add Customer' to create a customer record.")
        return

    st.caption("Click any row below (or use the quick selector) to open the full customer profile, bills, and payment actions.")
    selection = st.dataframe(
        pd.DataFrame(cust_rows),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="cust_directory_table",
    )

    sel_rows = selection.selection.rows if selection and hasattr(selection, "selection") else []
    if sel_rows:
        idx = sel_rows[0]
        if 0 <= idx < len(cust_meta):
            st.session_state.selected_customer_id = cust_meta[idx][0]
            st.rerun()

    col_p1, col_p2 = st.columns([3, 1])
    with col_p1:
        opts = {f"{m[1]} ({m[2]}) — {m[3]}": m[0] for m in cust_meta}
        chosen_lbl = st.selectbox("Open Customer Profile", options=list(opts.keys()), label_visibility="collapsed", key="cust_quick_sel")
    with col_p2:
        if st.button("Open Profile →", type="secondary", use_container_width=True, key="cust_quick_btn"):
            st.session_state.selected_customer_id = opts[chosen_lbl]
            st.rerun()
