"""
Add New Customer & Bill Entry Page for Krishna Colour – Asian Paints.
Clean, non-technical form with:
1. Customer Details (Name, Mobile Number, Full Address)
2. Bill Details (Manual Bill Number 1-5+ digits, Bill Date, Add Another Bill Number)
3. Items Purchased (Option A: Category -> Product -> Pack Size Dropdown OR Option B: Custom Textbox)
4. Amount Details (Original Amount [optional ref], Final Deal Amount, Amount Received)
"""
from datetime import date
from decimal import Decimal
import pandas as pd
import streamlit as st

from config.database import get_db
from components.header import render_header
from components.product_selector import render_item_entry_widget
from components.sidebar import navigate_to
from services.customer_service import (
    create_customer,
    DuplicateCustomerError,
    DuplicateBillNumberError,
    InvalidAmountError,
)
from auth.login import get_current_user
from utils.helpers import format_currency


def _init_add_customer_state():
    if "new_cust_bills_queue" not in st.session_state:
        st.session_state.new_cust_bills_queue = []
    if "new_bill_items_draft" not in st.session_state:
        st.session_state.new_bill_items_draft = []
    if "nc_cust_nonce" not in st.session_state:
        st.session_state.nc_cust_nonce = 0
    if "nc_bill_nonce" not in st.session_state:
        st.session_state.nc_bill_nonce = 0


def _clear_current_bill_fields():
    st.session_state.new_bill_items_draft = []
    st.session_state.nc_bill_nonce = st.session_state.get("nc_bill_nonce", 0) + 1


def _reset_add_customer_state():
    st.session_state.new_cust_bills_queue = []
    st.session_state.new_bill_items_draft = []
    st.session_state.nc_cust_nonce = st.session_state.get("nc_cust_nonce", 0) + 1
    st.session_state.nc_bill_nonce = st.session_state.get("nc_bill_nonce", 0) + 1


def render_add_customer_page():
    """Render structured Add Customer & Multi-Bill form."""
    render_header("Add Customer & Bill")
    user = get_current_user() or {"username": "admin", "role": "admin"}
    username = user.get("username", "admin")

    _init_add_customer_state()
    c_nonce = st.session_state.nc_cust_nonce
    b_nonce = st.session_state.nc_bill_nonce

    # SECTION 1: CUSTOMER DETAILS
    st.markdown('<div class="section-title">1. Customer Details</div>', unsafe_allow_html=True)
    with st.container(border=True):
        col1, col2 = st.columns([1.5, 1])
        with col1:
            cust_name = st.text_input("Customer Name *", placeholder="e.g. Rahul Patel", key=f"nc_name_{c_nonce}")
        with col2:
            cust_mobile = st.text_input("Mobile Number *", placeholder="10-digit mobile e.g. 9876543210", key=f"nc_mobile_{c_nonce}")

        cust_address = st.text_area("Full Address *", placeholder="House/Shop no, Street, City e.g. Rajkot", height=72, key=f"nc_address_{c_nonce}")
        cust_notes = st.text_input("Customer Notes (Optional)", placeholder="Contractor reference, site name...", key=f"nc_notes_{c_nonce}")

    # QUEUED BILLS PREVIEW (shown prominently if bills already queued)
    if st.session_state.new_cust_bills_queue:
        st.markdown('<div class="section-title">Queued Bills Ready to Save</div>', unsafe_allow_html=True)
        q_rows = []
        for idx, qb in enumerate(st.session_state.new_cust_bills_queue, start=1):
            pend = (qb["final_deal_amount"] - qb["amount_received"]) if qb.get("has_pending") else Decimal("0.00")
            pend = pend if pend > Decimal("0.00") else Decimal("0.00")
            q_rows.append({
                "#": idx,
                "Bill Number": qb["bill_number"],
                "Date": qb["bill_date"].strftime("%d-%b-%Y"),
                "Items": len(qb["items"]),
                "Final Deal Amount": format_currency(qb["final_deal_amount"]),
                "Amount Received": format_currency(qb["amount_received"]),
                "Pending Amount": format_currency(pend) if pend > 0 else "—",
                "Status": "Paid" if pend == 0 else "Payment Pending",
            })
        st.dataframe(pd.DataFrame(q_rows), use_container_width=True, hide_index=True)

        col_qrm1, col_qrm2 = st.columns([2, 1])
        with col_qrm1:
            q_rm_idx = st.selectbox(
                "Remove Queued Bill",
                options=list(range(1, len(st.session_state.new_cust_bills_queue) + 1)),
                format_func=lambda i: f"Bill #{st.session_state.new_cust_bills_queue[i-1]['bill_number']}",
                key="nc_rm_qbill_sel",
            )
        with col_qrm2:
            st.write("")
            if st.button("🗑️ Remove Queued Bill", key="nc_rm_qbill_btn", use_container_width=True):
                st.session_state.new_cust_bills_queue.pop(q_rm_idx - 1)
                st.rerun()

        st.info(
            "The bill(s) above are already queued. Leave the form below blank and click "
            "**💾 Save Customer & Bill(s)** at the bottom, OR enter another different bill number below."
        )

    # SECTION 2: CURRENT BILL & ITEMS
    st.markdown('<div class="section-title">2. Bill Details & Items</div>', unsafe_allow_html=True)
    with st.container(border=True):
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            bill_no = st.text_input(
                "Bill Number *",
                placeholder="Enter manual bill number (e.g. 244, 245, 12540)",
                key=f"nc_bill_no_{b_nonce}",
            )
        with col_b2:
            bill_dt = st.date_input("Bill Date *", value=date.today(), key=f"nc_bill_date_{b_nonce}")

        st.markdown("**Items Purchased**")
        with get_db() as db:
            added_item = render_item_entry_widget(db, key_prefix=f"nc_item_{b_nonce}")

        if added_item:
            st.session_state.new_bill_items_draft.append(added_item)
            st.rerun()

        if st.session_state.new_bill_items_draft:
            item_rows = []
            for idx, it in enumerate(st.session_state.new_bill_items_draft, start=1):
                item_rows.append({
                    "#": idx,
                    "Source": "Dropdown" if it["entry_type"] == "DROPDOWN" else "Custom",
                    "Category": it.get("category_name") or "—",
                    "Product / Item": it["product_name"],
                    "Pack Size": it.get("pack_size") or "—",
                    "Quantity": float(it["quantity"]),
                })
            st.dataframe(pd.DataFrame(item_rows), use_container_width=True, hide_index=True)

            col_rm1, col_rm2 = st.columns([2, 1])
            with col_rm1:
                rm_idx = st.selectbox(
                    "Remove Item #",
                    options=list(range(1, len(st.session_state.new_bill_items_draft) + 1)),
                    format_func=lambda i: f"#{i}: {st.session_state.new_bill_items_draft[i-1]['product_name']}",
                    key="nc_rm_item_sel",
                )
            with col_rm2:
                st.write("")
                if st.button("🗑️ Remove Selected Item", key="nc_rm_item_btn", use_container_width=True):
                    st.session_state.new_bill_items_draft.pop(rm_idx - 1)
                    st.rerun()
        else:
            st.caption("No items added to this bill yet. Use Option A (Dropdown) or Option B (Custom Item) above.")

        st.markdown("---")
        st.markdown("**3. Amount Details**")
        st.caption(
            "Enter Final Deal Amount and Amount Received. By default, there is NO pending balance "
            "and Amount Received closes the deal. Check 'Add Pending Amount (Optional)' only if payment is pending."
        )

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            final_deal_amt = st.number_input("Final Deal Amount (₹)", min_value=0.00, value=0.00, step=50.0, format="%.2f", key=f"nc_deal_amt_{b_nonce}")
        with col_a2:
            received_amt = st.number_input("Amount Received (₹) *", min_value=0.00, value=0.00, step=50.0, format="%.2f", key=f"nc_rec_amt_{b_nonce}")

        has_pending = st.checkbox("Add Pending Amount (Optional)", value=False, key=f"nc_has_pending_{b_nonce}")

        deal_dec = Decimal(str(final_deal_amt)).quantize(Decimal("0.01"))
        rec_dec = Decimal(str(received_amt)).quantize(Decimal("0.01"))
        if has_pending:
            if rec_dec > deal_dec:
                st.error(f"⚠️ Amount Received ({format_currency(rec_dec)}) cannot exceed Final Deal Amount ({format_currency(deal_dec)}).")
            else:
                pending_dec = deal_dec - rec_dec
                if pending_dec == Decimal("0.00"):
                    st.success(f"No Pending Amount — **Paid (Closed)** ({format_currency(rec_dec)})")
                else:
                    st.warning(f"Payment Status: **Payment Pending** — Pending Amount: **{format_currency(pending_dec)}**")
        else:
            if deal_dec > Decimal("0.00") or rec_dec > Decimal("0.00"):
                st.success(f"Done & Closed (**Paid**) — Final Received Amount: **{format_currency(rec_dec)}** (No Pending)")

        bill_notes = st.text_input("Bill Notes (Optional)", placeholder="Shade code, delivery remarks...", key=f"nc_bill_notes_{b_nonce}")

        if st.button("➕ Queue This Bill & Add Another Bill Number", use_container_width=True, key="nc_queue_bill_btn"):
            clean_b = (bill_no or "").strip()
            if not clean_b:
                st.error("Please enter a Bill Number before adding another bill.")
            elif any(b["bill_number"].lower() == clean_b.lower() for b in st.session_state.new_cust_bills_queue):
                st.warning(f"⚠️ Bill Number '{clean_b}' is already queued above for this customer.")
            elif has_pending and rec_dec > deal_dec:
                st.error("Amount Received cannot exceed Final Deal Amount when Pending Amount is enabled.")
            else:
                st.session_state.new_cust_bills_queue.append({
                    "bill_number": clean_b,
                    "bill_date": bill_dt,
                    "final_deal_amount": deal_dec,
                    "amount_received": rec_dec,
                    "has_pending": has_pending,
                    "items": list(st.session_state.new_bill_items_draft),
                    "notes": bill_notes,
                })
                _clear_current_bill_fields()
                st.success(f"Bill #{clean_b} queued! Enter the next bill number or click 'Save Customer & Bill(s)' below.")
                st.rerun()

    st.markdown("---")
    col_save, col_clear = st.columns([3, 1])
    with col_save:
        if st.button("💾 Save Customer & Bill(s)", type="primary", use_container_width=True, key="nc_save_all"):
            bills_to_save = list(st.session_state.new_cust_bills_queue)
            clean_curr_bill = (bill_no or "").strip()

            if clean_curr_bill:
                if any(b["bill_number"].lower() == clean_curr_bill.lower() for b in bills_to_save):
                    st.error(
                        f"⚠️ Bill Number '{clean_curr_bill}' is already in 'Queued Bills Ready to Save' above. "
                        "Clear the Bill Number field below (or enter a different bill number) and click Save again."
                    )
                    st.stop()
                if has_pending and rec_dec > deal_dec:
                    st.error("Amount Received cannot exceed Final Deal Amount when Pending Amount is enabled.")
                    st.stop()
                bills_to_save.append({
                    "bill_number": clean_curr_bill,
                    "bill_date": bill_dt,
                    "final_deal_amount": deal_dec,
                    "amount_received": rec_dec,
                    "has_pending": has_pending,
                    "items": list(st.session_state.new_bill_items_draft),
                    "notes": bill_notes,
                })
            elif st.session_state.new_bill_items_draft or deal_dec > Decimal("0.00") or rec_dec > Decimal("0.00"):
                st.error("Please enter a Bill Number for the current bill details before saving.")
                st.stop()

            try:
                with get_db() as db:
                    new_cust = create_customer(
                        db=db,
                        name=cust_name,
                        mobile=cust_mobile,
                        address=cust_address,
                        bills_data=bills_to_save,
                        notes=cust_notes,
                        username=username,
                    )
                    new_cid = new_cust.id
                    new_code = new_cust.customer_code
                    new_cname = new_cust.name

                _reset_add_customer_state()
                st.session_state.selected_customer_id = new_cid
                navigate_to("Customers")
                st.success(f"Customer '{new_cname}' ({new_code}) saved successfully!")
                st.rerun()
            except (DuplicateCustomerError, DuplicateBillNumberError, InvalidAmountError, ValueError) as ve:
                st.error(str(ve))
            except Exception as e:
                st.error(f"Could not save customer: {str(e)}")

    with col_clear:
        if st.button("Reset Form", type="secondary", use_container_width=True, key="nc_reset_btn"):
            _reset_add_customer_state()
            st.rerun()
