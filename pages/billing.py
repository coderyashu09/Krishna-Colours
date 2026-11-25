"""
Billing & Payments Module.
Supports Manual and Automatic Bill Numbering, Duplicate Prevention, Multi-Product Line Items,
Precise Decimal Calculations, ReportLab PDF Invoices, Automatic Stock Decrement on Finalization,
Exact-once Stock Reversal on Cancellation, and Dedicated Payment Collection.
"""
from datetime import datetime, date
from decimal import Decimal
import io
import streamlit as st
import pandas as pd
from sqlalchemy import select

from config.database import get_db
from database.models import Bill, Customer, Product, Payment
from components.header import render_header
from components.cards import render_kpi_card, status_pill_html
from services.billing_service import (
    create_bill, cancel_bill, get_bills, generate_bill_number, DuplicateBillNumberError
)
from services.payment_service import record_payment, reverse_payment, get_payments, OverpaymentError
from services.inventory_service import get_products, NegativeStockError
from auth.login import get_current_user, user_can
from utils.pdf_generator import generate_bill_pdf
from utils.excel_handler import export_dataframe_to_excel
from utils.helpers import format_currency


def render_billing_page():
    """Render comprehensive billing and payments management interface."""
    render_header("Billing & Payments")
    user = get_current_user() or {"id": 1, "username": "admin", "role": "admin"}
    is_admin = (user.get("role") == "admin")

    tab_create, tab_bills, tab_pay, tab_receipts = st.tabs([
        "🧾 New Invoice (POS)",
        "📋 Invoices History",
        "💳 Collect Payment",
        "📜 Payment Receipts",
    ])

    # 1. CREATE BILL TAB
    with tab_create:
        st.subheader("Create New Customer Bill")
        st.caption("Generate a professional retail or contractor invoice. Stock is automatically decremented upon finalization.")

        with get_db() as db:
            customers = db.execute(select(Customer).where(Customer.is_deleted == False).order_by(Customer.name.asc())).scalars().all()
            products = get_products(db, include_deleted=False)

        if not customers:
            st.warning("⚠️ Please register at least one customer before creating an invoice.")
        elif not products:
            st.warning("⚠️ No products available in catalog. Please add products first.")
        else:
            # Customer Selection & Bill Numbering Setup
            col_c1, col_c2, col_c3 = st.columns([2, 1, 1])
            with col_c1:
                cust_options = {f"{c.name} ({c.customer_code}) – {c.mobile}": c.id for c in customers}
                selected_cust_label = st.selectbox("Select Customer *", options=list(cust_options.keys()), key="bill_cust_select")
                selected_customer_id = cust_options[selected_cust_label]

            with col_c2:
                num_mode = st.radio("Bill Numbering", options=["Automatic", "Manual"], horizontal=True)

            with col_c3:
                if num_mode == "Manual":
                    bill_number_input = st.text_input("Bill Number *", placeholder="e.g. 244, 245, 246", key="manual_bill_no")
                else:
                    with get_db() as db:
                        auto_preview = generate_bill_number(db)
                    st.text_input("Auto Generated Bill #", value=auto_preview, disabled=True)
                    bill_number_input = None

            bill_date_input = st.date_input("Bill Date", value=date.today(), key="bill_date_val")

            st.markdown("---")
            st.markdown("##### Add Products to Invoice")

            # Initialize line items in session state
            if "bill_items" not in st.session_state:
                st.session_state.bill_items = []

            # Add Item Row
            col_ip, col_iq, col_ir, col_id, col_iaction = st.columns([3, 1, 1, 1, 1])
            with col_ip:
                prod_map = {f"{p.name} ({p.product_code}) - Stock: {p.current_stock} {p.unit}": p for p in products}
                chosen_prod_label = st.selectbox("Select Product", options=list(prod_map.keys()), key="add_item_select")
                chosen_product = prod_map[chosen_prod_label]
            with col_iq:
                item_qty = st.number_input("Quantity", min_value=0.01, value=1.00, step=1.0, format="%.2f", key="add_item_qty")
            with col_ir:
                item_rate = st.number_input("Rate (₹)", min_value=0.00, value=float(chosen_product.selling_price), step=10.0, format="%.2f", key="add_item_rate")
            with col_id:
                item_disc = st.number_input("Discount (₹)", min_value=0.00, value=0.00, step=10.0, format="%.2f", key="add_item_disc")
            with col_iaction:
                st.write("")
                st.write("")
                if st.button("➕ Add Item", key="btn_add_line_item", use_container_width=True):
                    st.session_state.bill_items.append({
                        "product_id": chosen_product.id,
                        "product_name": chosen_product.name,
                        "quantity": Decimal(str(item_qty)),
                        "unit_price": Decimal(str(item_rate)),
                        "discount_amount": Decimal(str(item_disc)),
                        "line_total": (Decimal(str(item_qty)) * Decimal(str(item_rate))) - Decimal(str(item_disc)),
                    })
                    st.rerun()

            # Display Line Items Table
            if st.session_state.bill_items:
                st.markdown("###### Invoice Line Items:")
                item_table_data = []
                for idx, item in enumerate(st.session_state.bill_items, start=1):
                    item_table_data.append({
                        "#": idx,
                        "Product Name": item["product_name"],
                        "Quantity": float(item["quantity"]),
                        "Rate (₹)": float(item["unit_price"]),
                        "Discount (₹)": float(item["discount_amount"]),
                        "Line Total (₹)": float(item["line_total"]),
                    })
                st.dataframe(pd.DataFrame(item_table_data), use_container_width=True, hide_index=True)

                col_clear, col_space = st.columns([1, 4])
                with col_clear:
                    if st.button("🗑️ Clear Items", key="btn_clear_items"):
                        st.session_state.bill_items = []
                        st.rerun()

                # Financial Calculations
                subtotal_calc = sum((it["line_total"] for it in st.session_state.bill_items), Decimal("0.00"))

                st.markdown("---")
                col_calc1, col_calc2 = st.columns([1, 1])

                with col_calc1:
                    bill_discount = st.number_input("Overall Bill Discount (₹)", min_value=0.00, value=0.00, step=50.0, format="%.2f")
                    tax_percentage = st.number_input("GST / Tax Percentage (%)", min_value=0.00, max_value=28.00, value=0.00, step=1.0, format="%.2f")
                    notes_bill = st.text_area("Bill Notes / Site Reference", placeholder="Asian Paints shade code, colorant recipe, customer instructions...")

                with col_calc2:
                    taxable = subtotal_calc - Decimal(str(bill_discount))
                    if taxable < Decimal("0.00"):
                        taxable = Decimal("0.00")
                    tax_amt_calc = (taxable * Decimal(str(tax_percentage)) / Decimal("100.00")).quantize(Decimal("0.01"))
                    grand_total_calc = (taxable + tax_amt_calc).quantize(Decimal("0.01"))

                    st.markdown(
                        f"""
                        <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 15px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                                <span>Subtotal:</span><strong>{format_currency(subtotal_calc)}</strong>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 6px; color: #DC2626;">
                                <span>Discount:</span><strong>-{format_currency(bill_discount)}</strong>
                            </div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                                <span>Tax ({tax_percentage}%):</span><strong>{format_currency(tax_amt_calc)}</strong>
                            </div>
                            <hr style="margin: 8px 0; border: none; border-top: 1px solid #E5E7EB;" />
                            <div style="display: flex; justify-content: space-between; font-size: 18px; color: #172033; font-weight: 700;">
                                <span>Grand Total:</span><span style="color: #2563EB;">{format_currency(grand_total_calc)}</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    st.markdown("##### Payment on Billing")
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        initial_pay = st.number_input("Amount Received Now (₹)", min_value=0.00, max_value=float(grand_total_calc), value=float(grand_total_calc), step=100.0, format="%.2f")
                    with col_p2:
                        pay_method = st.selectbox("Payment Method", options=["CASH", "UPI", "BANK_TRANSFER", "CHEQUE", "OTHER"])

                    pay_ref = st.text_input("UPI / Cheque / Transaction Ref", placeholder="e.g. UTR / UPI Ref / Cheque #")

                    bill_state = st.selectbox("Bill Lifecycle State", options=["FINALIZED", "DRAFT"], help="Finalized bills immediately deduct stock and update customer ledgers.")

                # Final Submit Button
                st.markdown("---")
                allow_neg_bill = False
                if is_admin:
                    allow_neg_bill = st.checkbox("Admin Override: Allow negative stock if item stock is insufficient", value=False, key="bill_neg_override")

                if st.button("🚀 Finalize & Print Bill", type="primary", use_container_width=True):
                    if num_mode == "Manual" and (not bill_number_input or not bill_number_input.strip()):
                        st.error("Please enter a valid manual bill number.")
                    else:
                        try:
                            with get_db() as db:
                                new_bill = create_bill(
                                    db=db,
                                    customer_id=selected_customer_id,
                                    items_data=st.session_state.bill_items,
                                    bill_number=bill_number_input.strip() if bill_number_input else None,
                                    bill_date=bill_date_input,
                                    discount=Decimal(str(bill_discount)),
                                    tax_rate=Decimal(str(tax_percentage)),
                                    initial_payment_amount=Decimal(str(initial_pay)),
                                    payment_method=pay_method,
                                    payment_reference=pay_ref,
                                    notes=notes_bill,
                                    bill_status=bill_state,
                                    allow_negative_stock=allow_neg_bill,
                                    user_id=user.get("id"),
                                    username=user.get("username", "admin"),
                                )

                            # Clear form session
                            st.session_state.bill_items = []
                            st.session_state.last_created_bill_id = new_bill.id
                            st.success(f"Bill #{new_bill.bill_number} finalized successfully! Grand Total: {format_currency(new_bill.grand_total)}")
                            st.rerun()

                        except DuplicateBillNumberError as dne:
                            st.error(f"Duplicate Bill Number: {str(dne)}")
                        except NegativeStockError as nse:
                            st.error(f"Insufficient Stock: {str(nse)}")
                        except Exception as e:
                            st.error(f"Failed to create bill: {str(e)}")

            else:
                st.info("No items added yet. Select a product and click 'Add Item' above.")

    # 2. BILLS HISTORY TAB
    with tab_bills:
        st.subheader("Invoice History & Management")
        st.caption("Search, filter, reprint PDF invoices, or safely cancel bills.")

        col_fb_s, col_fb_status, col_fb_pay = st.columns([2, 1, 1])
        with col_fb_s:
            search_b = st.text_input("🔍 Search Invoices", placeholder="Bill # (e.g. 244), Customer Name or Phone...")
        with col_fb_status:
            filter_b_status = st.selectbox("Bill Status", options=["All", "FINALIZED", "DRAFT", "CANCELLED"])
        with col_fb_pay:
            filter_b_pay = st.selectbox("Payment Status", options=["All", "PAID", "PARTIALLY_PAID", "PENDING"])

        with get_db() as db:
            bills_list = get_bills(
                db,
                search=search_b,
                bill_status=filter_b_status,
                payment_status=filter_b_pay,
            )

        if not bills_list:
            st.info("No bills found matching filters.")
        else:
            b_data = []
            for b in bills_list:
                b_data.append({
                    "Bill #": b.bill_number,
                    "Date": b.bill_date.strftime("%Y-%m-%d"),
                    "Customer": b.customer.name,
                    "Grand Total (₹)": float(b.grand_total),
                    "Received (₹)": float(b.amount_received),
                    "Outstanding (₹)": float(b.outstanding_amount),
                    "Payment Status": b.payment_status,
                    "Bill Status": b.bill_status,
                })
            df_b = pd.DataFrame(b_data)
            st.dataframe(df_b, use_container_width=True, hide_index=True)

            # Export Bills to Excel
            excel_bills_bytes = export_dataframe_to_excel(df_b, sheet_name="Invoices", title="Krishna Colour - Invoices History")
            st.download_button(
                "📥 Export Invoices History (Excel)",
                data=excel_bills_bytes,
                file_name=f"krishna_colour_invoices_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            st.markdown("---")
            st.subheader("Invoice Actions: PDF Print & Cancellation")

            bill_map = {f"Bill #{b.bill_number} – {b.customer.name} ({format_currency(b.grand_total)})": b.id for b in bills_list}
            selected_bill_label = st.selectbox("Select Invoice", options=list(bill_map.keys()))
            selected_bill_id = bill_map[selected_bill_label]

            with get_db() as db:
                chosen_bill = db.execute(select(Bill).where(Bill.id == selected_bill_id)).scalar_one()

            col_pdf, col_cancel = st.columns([1, 1])

            with col_pdf:
                st.markdown("##### 📄 Printable PDF Invoice")
                pdf_bytes = generate_bill_pdf(chosen_bill)
                st.download_button(
                    label=f"🖨️ Download / Print Bill #{chosen_bill.bill_number} (PDF)",
                    data=pdf_bytes,
                    file_name=f"Invoice_{chosen_bill.bill_number}_{chosen_bill.customer.name.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )

            with col_cancel:
                st.markdown("##### ⚠️ Cancel Invoice")
                if chosen_bill.bill_status == "CANCELLED":
                    st.warning(f"Bill #{chosen_bill.bill_number} is already CANCELLED.")
                elif not is_admin:
                    st.info("Invoice cancellation requires Administrator privileges.")
                else:
                    cancel_reason = st.text_input("Cancellation Reason *", placeholder="e.g. Order cancelled by customer, billing entry error...")
                    if st.button("🚨 Cancel Bill & Reverse Stock", type="secondary", use_container_width=True):
                        if not cancel_reason.strip():
                            st.error("Please enter a valid cancellation reason.")
                        else:
                            try:
                                with get_db() as db:
                                    cancel_bill(
                                        db=db,
                                        bill_id=chosen_bill.id,
                                        reason=cancel_reason.strip(),
                                        user_id=user.get("id"),
                                        username=user.get("username", "admin"),
                                    )
                                st.success(f"Bill #{chosen_bill.bill_number} cancelled! Stock restored.")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Cancellation failed: {str(ex)}")

    # 3. COLLECT PAYMENT TAB
    with tab_pay:
        st.subheader("Collect Payment Against Invoice")
        st.caption("Record incoming customer payments (Cash, UPI, Cheque, Bank Transfer) against pending dues.")

        with get_db() as db:
            unpaid_bills = list(
                db.execute(
                    select(Bill)
                    .where(Bill.bill_status == "FINALIZED", Bill.outstanding_amount > 0)
                    .order_by(Bill.bill_date.desc())
                ).scalars().all()
            )

        if not unpaid_bills:
            st.success("🎉 All customer bills are fully paid! No outstanding dues.")
        else:
            bill_choice_map = {
                f"Bill #{b.bill_number} – {b.customer.name} | Total: {format_currency(b.grand_total)} | Outstanding: {format_currency(b.outstanding_amount)}": b.id
                for b in unpaid_bills
            }
            chosen_unpaid_label = st.selectbox("Select Bill to Pay *", options=list(bill_choice_map.keys()))
            target_bill_id = bill_choice_map[chosen_unpaid_label]

            with get_db() as db:
                target_bill = db.execute(select(Bill).where(Bill.id == target_bill_id)).scalar_one()

            with st.form("collect_payment_form", clear_on_submit=True):
                col_p_amt, col_p_date = st.columns(2)
                with col_p_amt:
                    pay_amount = st.number_input(
                        "Payment Amount (₹) *",
                        min_value=0.01,
                        max_value=float(target_bill.outstanding_amount),
                        value=float(target_bill.outstanding_amount),
                        step=100.0,
                        format="%.2f"
                    )
                with col_p_date:
                    pay_date = st.date_input("Payment Date", value=date.today())

                col_pm, col_pr = st.columns(2)
                with col_pm:
                    pay_method_sel = st.selectbox("Payment Method *", options=["CASH", "UPI", "BANK_TRANSFER", "CHEQUE", "OTHER"])
                with col_pr:
                    txn_ref = st.text_input("Transaction Reference / Cheque #", placeholder="e.g. UPI Ref / Bank UTR #")

                pay_notes = st.text_area("Receipt Notes", placeholder="e.g. Part payment received via phonepe...")

                allow_overpay = False
                if is_admin:
                    allow_overpay = st.checkbox("Admin Override: Allow payment exceeding bill outstanding balance", value=False)

                submit_pay = st.form_submit_button("💳 Confirm Payment Collection", type="primary", use_container_width=True)

                if submit_pay:
                    try:
                        with get_db() as db:
                            payment_rec = record_payment(
                                db=db,
                                customer_id=target_bill.customer_id,
                                amount=Decimal(str(pay_amount)),
                                bill_id=target_bill.id,
                                payment_date=pay_date,
                                payment_method=pay_method_sel,
                                transaction_reference=txn_ref,
                                notes=pay_notes,
                                allow_overpayment=allow_overpay,
                                user_id=user.get("id"),
                                username=user.get("username", "admin"),
                            )
                        st.success(f"Payment of {format_currency(pay_amount)} recorded! Receipt #{payment_rec.payment_number}")
                        st.rerun()
                    except OverpaymentError as oe:
                        st.error(f"Overpayment blocked: {str(oe)}")
                    except Exception as e:
                        st.error(f"Payment recording failed: {str(e)}")

    # 4. PAYMENT RECEIPTS TAB
    with tab_receipts:
        st.subheader("Payment Collection Register & Receipts")
        st.caption("Chronological record of all payment transactions received across all customers.")

        with get_db() as db:
            payments_list = get_payments(db, include_reversals=True)

        if not payments_list:
            st.info("No payment transactions recorded yet.")
        else:
            p_data = []
            for p in payments_list:
                status_p = "REVERSED" if p.is_reversal else "SUCCESS"
                p_data.append({
                    "Receipt #": p.payment_number,
                    "Date": p.payment_date.strftime("%Y-%m-%d"),
                    "Customer": p.customer.name,
                    "Bill #": p.bill.bill_number if p.bill else "On Account",
                    "Amount (₹)": float(p.amount),
                    "Method": p.payment_method,
                    "Reference": p.transaction_reference or "-",
                    "Status": status_p,
                    "Notes": p.notes or "",
                })
            df_pay = pd.DataFrame(p_data)
            st.dataframe(df_pay, use_container_width=True, hide_index=True)

            # Export Excel
            excel_pay_bytes = export_dataframe_to_excel(df_pay, sheet_name="Payments", title="Krishna Colour - Payment Receipts Register")
            st.download_button(
                "📥 Export Payments Register (Excel)",
                data=excel_pay_bytes,
                file_name=f"krishna_colour_payments_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Reverse Payment Action for Admin
            if is_admin:
                st.markdown("---")
                st.subheader("Admin: Payment Reversal / Refund")
                active_receipts = [p for p in payments_list if not p.is_reversal]
                if active_receipts:
                    rec_map = {f"{p.payment_number} – {p.customer.name} ({format_currency(p.amount)}) | {p.payment_date}": p.id for p in active_receipts}
                    chosen_rec_label = st.selectbox("Select Receipt to Reverse", options=list(rec_map.keys()))
                    chosen_rec_id = rec_map[chosen_rec_label]

                    rev_reason = st.text_input("Reversal Reason *", placeholder="e.g. Bounced cheque, duplicate payment entry...")
                    if st.button("⚠️ Reverse Payment", type="secondary"):
                        if not rev_reason.strip():
                            st.error("Please enter a reversal reason.")
                        else:
                            try:
                                with get_db() as db:
                                    reverse_payment(
                                        db=db,
                                        payment_id=chosen_rec_id,
                                        reason=rev_reason.strip(),
                                        user_id=user.get("id"),
                                        username=user.get("username", "admin"),
                                    )
                                st.success("Payment transaction successfully reversed and customer balance updated.")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Reversal failed: {str(ex)}")
