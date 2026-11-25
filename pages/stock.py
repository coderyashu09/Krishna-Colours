"""
Stock Management Page: Stock In, Stock Out, Movement Ledger, and Transaction Reversals.
Enforces negative stock prevention and accurate inventory updates.
"""
from datetime import date, datetime
from decimal import Decimal
import streamlit as st
import pandas as pd
from sqlalchemy import select

from config.database import get_db
from database.models import Product, StockTransaction, Supplier
from components.header import render_header
from components.cards import render_kpi_card
from services.inventory_service import (
    record_stock_in, record_stock_out, cancel_stock_transaction,
    get_products, NegativeStockError
)
from auth.login import user_can, get_current_user
from utils.excel_handler import export_dataframe_to_excel
from utils.helpers import format_currency


def render_stock_page():
    """Render Stock Management operations."""
    render_header("Stock Management")
    user = get_current_user() or {"id": 1, "username": "admin", "role": "admin"}
    is_admin_user = (user.get("role") == "admin")

    with get_db() as db:
        products = get_products(db)
        product_options = {f"{p.name} ({p.product_code}) - Stock: {p.current_stock} {p.unit}": p.id for p in products}

    stock_tabs = st.tabs([
        "📥 Stock In (Receive)",
        "📤 Stock Out (Issue/Deduct)",
        "📜 Movement History",
        "↩️ Transaction Reversal",
    ])

    # TAB 1: STOCK IN
    with stock_tabs[0]:
        st.subheader("Record Products Received (Stock In)")
        st.caption("Record new paint batches, primers, or tools received from Asian Paints or suppliers.")

        if not product_options:
            st.warning("No products found in the catalog. Please add products first under the 'Products' tab.")
        else:
            with st.form("stock_in_form", clear_on_submit=True):
                col_p, col_q = st.columns([2, 1])
                with col_p:
                    selected_prod_label = st.selectbox("Select Product *", options=list(product_options.keys()))
                    product_id = product_options[selected_prod_label]
                with col_q:
                    qty_in = st.number_input("Quantity Received *", min_value=0.01, step=1.0, format="%.2f")

                col_rate, col_supp, col_inv = st.columns(3)
                with col_rate:
                    purchase_rate = st.number_input("Purchase Price / Rate (₹) *", min_value=0.00, step=10.0, format="%.2f")
                with col_supp:
                    supplier = st.text_input("Supplier / Distributor Name", value="Asian Paints Depot")
                with col_inv:
                    inv_no = st.text_input("Supplier Invoice / Delivery Challan #")

                notes_in = st.text_area("Notes / Batch Details", placeholder="Batch number, container condition, tinting base info...")

                submitted_in = st.form_submit_button("📥 Confirm & Add Stock", use_container_width=True, type="primary")

                if submitted_in:
                    try:
                        with get_db() as db:
                            tx = record_stock_in(
                                db=db,
                                product_id=product_id,
                                quantity=Decimal(str(qty_in)),
                                purchase_price=Decimal(str(purchase_rate)),
                                supplier_name=supplier,
                                invoice_number=inv_no,
                                notes=notes_in,
                                user_id=user.get("id"),
                                username=user.get("username", "admin"),
                            )
                        st.success(f"Stock added successfully! Transaction: {tx.transaction_code}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to record Stock In: {str(e)}")

    # TAB 2: STOCK OUT
    with stock_tabs[1]:
        st.subheader("Record Products Leaving Stock (Stock Out)")
        st.caption("Record direct issues, shop usage, damaged goods, or direct cash sales.")

        if not product_options:
            st.warning("No products available.")
        else:
            with st.form("stock_out_form", clear_on_submit=True):
                col_p_out, col_q_out = st.columns([2, 1])
                with col_p_out:
                    selected_prod_label_out = st.selectbox("Select Product *", options=list(product_options.keys()), key="stock_out_p")
                    product_id_out = product_options[selected_prod_label_out]
                with col_q_out:
                    qty_out = st.number_input("Quantity Out *", min_value=0.01, step=1.0, format="%.2f", key="stock_out_q")

                col_party, col_ref, col_rate_out = st.columns(3)
                with col_party:
                    party = st.text_input("Recipient / Customer / Usage", placeholder="Contractor name or Store tinting...")
                with col_ref:
                    ref_no = st.text_input("Reference # / Voucher #")
                with col_rate_out:
                    selling_rate = st.number_input("Selling / Transfer Rate (₹)", min_value=0.00, step=10.0, format="%.2f")

                notes_out = st.text_area("Notes / Reason for Stock Out", placeholder="Damaged container, shop sample, or contractor issue...", key="notes_out")

                override_neg = False
                if is_admin_user:
                    override_neg = st.checkbox("⚠️ Admin Override: Allow Negative Stock if insufficient inventory", value=False)

                submitted_out = st.form_submit_button("📤 Confirm & Deduct Stock", use_container_width=True, type="primary")

                if submitted_out:
                    try:
                        with get_db() as db:
                            tx = record_stock_out(
                                db=db,
                                product_id=product_id_out,
                                quantity=Decimal(str(qty_out)),
                                selling_price=Decimal(str(selling_rate)) if selling_rate > 0 else None,
                                party_name=party,
                                reference_type="MANUAL",
                                reference_id=ref_no,
                                notes=notes_out,
                                override_negative=override_neg,
                                user_id=user.get("id"),
                                username=user.get("username", "admin"),
                            )
                        st.success(f"Stock deducted successfully! Transaction: {tx.transaction_code}")
                        st.rerun()
                    except NegativeStockError as nse:
                        st.error(f"Stock Error: {str(nse)}")
                    except Exception as e:
                        st.error(f"Failed to record Stock Out: {str(e)}")

    # TAB 3: MOVEMENT HISTORY
    with stock_tabs[2]:
        st.subheader("Stock Movement History & Audit Log")
        st.caption("Chronological ledger of all inventory additions, deductions, sales, and reversals.")

        col_f_type, col_f_search = st.columns([1, 2])
        with col_f_type:
            tx_type_filter = st.selectbox(
                "Filter Transaction Type",
                options=["All", "STOCK_IN", "STOCK_OUT", "BILL_SALE", "SHOP_ISSUE", "SHOP_RETURN", "BILL_CANCEL"]
            )
        with col_f_search:
            search_query = st.text_input("Search by Product, Supplier, Party or Reference Code")

        with get_db() as db:
            q = select(StockTransaction).join(Product, Product.id == StockTransaction.product_id)
            if tx_type_filter != "All":
                q = q.where(StockTransaction.transaction_type == tx_type_filter)
            if search_query.strip():
                term = f"%{search_query.strip()}%"
                q = q.where(
                    (Product.name.ilike(term)) |
                    (StockTransaction.party_name.ilike(term)) |
                    (StockTransaction.transaction_code.ilike(term)) |
                    (StockTransaction.reference_id.ilike(term))
                )
            q = q.order_by(StockTransaction.created_at.desc()).limit(150)
            transactions = list(db.execute(q).scalars().all())

        if not transactions:
            st.info("No stock transactions found matching the selected filters.")
        else:
            tx_data = []
            for t in transactions:
                status_str = "CANCELLED" if t.is_cancelled else "CONFIRMED"
                tx_data.append({
                    "TX Code": t.transaction_code,
                    "Date & Time": t.created_at.strftime("%Y-%m-%d %H:%M"),
                    "Type": t.transaction_type,
                    "Product Name": t.product.name,
                    "Quantity": f"{t.quantity:.2f} {t.product.unit}",
                    "Rate (₹)": float(t.unit_price or 0.0),
                    "Party / Supplier": t.party_name or "-",
                    "Reference": t.reference_id or "-",
                    "Status": status_str,
                    "Notes": t.notes or "",
                })
            df_tx = pd.DataFrame(tx_data)
            st.dataframe(df_tx, use_container_width=True, hide_index=True)

            # Export Excel
            excel_bytes = export_dataframe_to_excel(df_tx, sheet_name="Stock Movements", title="Krishna Colour - Stock Movement Ledger")
            st.download_button(
                "📥 Export Stock History (Excel)",
                data=excel_bytes,
                file_name=f"krishna_colour_stock_history_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # TAB 4: REVERSAL
    with stock_tabs[3]:
        st.subheader("Cancel & Reverse Stock Transaction")
        st.caption("Authorized reversal of erroneous stock in/out records. Restores inventory balance exactly once.")

        if not is_admin_user:
            st.warning("⚠️ Only Administrators have permission to cancel and reverse stock transactions.")
        else:
            with get_db() as db:
                recent_active_tx = list(
                    db.execute(
                        select(StockTransaction)
                        .where(StockTransaction.is_cancelled == False)
                        .order_by(StockTransaction.created_at.desc())
                        .limit(50)
                    ).scalars().all()
                )

            if not recent_active_tx:
                st.info("No active reversible transactions found.")
            else:
                tx_map = {
                    f"{t.transaction_code} | {t.transaction_type} | {t.product.name} ({t.quantity} {t.product.unit}) | {t.created_at.strftime('%Y-%m-%d')}": t.id
                    for t in recent_active_tx
                }
                selected_tx_label = st.selectbox("Select Transaction to Cancel & Reverse", options=list(tx_map.keys()))
                tx_id_to_cancel = tx_map[selected_tx_label]

                reversal_reason = st.text_input("Reason for Reversal *", placeholder="e.g. Invoicing error, wrong quantity entered, supplier returned goods...")
                override_reversal_neg = st.checkbox("Allow negative stock on reversal if required", value=False)

                if st.button("⚠️ Confirm Cancellation & Reverse Stock", type="primary"):
                    if not reversal_reason.strip():
                        st.error("Please enter a valid reason for cancellation.")
                    else:
                        try:
                            with get_db() as db:
                                cancelled_tx = cancel_stock_transaction(
                                    db=db,
                                    transaction_id=tx_id_to_cancel,
                                    reason=reversal_reason.strip(),
                                    override_negative=override_reversal_neg,
                                    user_id=user.get("id"),
                                    username=user.get("username", "admin"),
                                )
                            st.success(f"Transaction {cancelled_tx.transaction_code} has been successfully cancelled and its stock effect reversed!")
                            st.rerun()
                        except NegativeStockError as nse:
                            st.error(f"Reversal blocked: {str(nse)}")
                        except Exception as e:
                            st.error(f"Reversal failed: {str(e)}")
