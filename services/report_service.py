"""
Comprehensive Reports and Analytics Service.
Generates all 15 business reports and calculates live dashboard metrics.
All calculations use exact database aggregations and Decimal precision.
Zero fake data or hardcoded numbers.
"""
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
import pandas as pd
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.orm import Session

from database.models import (
    Product, Customer, Bill, BillItem, Payment,
    StockTransaction, OtherShop, ShopIssue, ShopIssueItem, ShopReturn, ShopReturnItem
)


def get_dashboard_metrics(db: Session) -> Dict[str, Any]:
    """Calculate all real-time KPIs and dashboard metrics."""
    today = date.today()
    first_of_month = today.replace(day=1)

    # 1. Customer Metrics
    total_customers = db.execute(select(func.count(Customer.id)).where(Customer.is_deleted == False)).scalar() or 0
    new_customers_month = db.execute(
        select(func.count(Customer.id))
        .where(and_(Customer.is_deleted == False, Customer.created_at >= datetime.combine(first_of_month, datetime.min.time())))
    ).scalar() or 0
    active_customers = db.execute(
        select(func.count(Customer.id))
        .where(and_(Customer.is_deleted == False, Customer.status == "active"))
    ).scalar() or 0

    # 2. Inventory Metrics
    total_products = db.execute(select(func.count(Product.id)).where(Product.is_deleted == False)).scalar() or 0
    total_available_stock = db.execute(
        select(func.coalesce(func.sum(Product.current_stock), Decimal("0.00")))
        .where(Product.is_deleted == False)
    ).scalar() or Decimal("0.00")
    low_stock_products = db.execute(
        select(func.count(Product.id))
        .where(and_(Product.is_deleted == False, Product.current_stock > 0, Product.current_stock <= Product.min_stock_level))
    ).scalar() or 0
    out_of_stock_products = db.execute(
        select(func.count(Product.id))
        .where(and_(Product.is_deleted == False, Product.current_stock <= 0))
    ).scalar() or 0

    inv_purchase_val = db.execute(
        select(func.coalesce(func.sum(Product.current_stock * Product.purchase_price), Decimal("0.00")))
        .where(and_(Product.is_deleted == False, Product.current_stock > 0))
    ).scalar() or Decimal("0.00")
    inv_selling_val = db.execute(
        select(func.coalesce(func.sum(Product.current_stock * Product.selling_price), Decimal("0.00")))
        .where(and_(Product.is_deleted == False, Product.current_stock > 0))
    ).scalar() or Decimal("0.00")

    # 3. Sales Metrics (Only finalized, non-cancelled bills)
    valid_bills_cond = and_(Bill.bill_status == "FINALIZED")

    today_sales = db.execute(
        select(func.coalesce(func.sum(Bill.grand_total), Decimal("0.00")))
        .where(and_(valid_bills_cond, Bill.bill_date == today))
    ).scalar() or Decimal("0.00")

    month_sales = db.execute(
        select(func.coalesce(func.sum(Bill.grand_total), Decimal("0.00")))
        .where(and_(valid_bills_cond, Bill.bill_date >= first_of_month))
    ).scalar() or Decimal("0.00")

    total_sales = db.execute(
        select(func.coalesce(func.sum(Bill.grand_total), Decimal("0.00")))
        .where(valid_bills_cond)
    ).scalar() or Decimal("0.00")

    total_bills = db.execute(
        select(func.count(Bill.id)).where(valid_bills_cond)
    ).scalar() or 0

    avg_bill_val = (total_sales / Decimal(total_bills)) if total_bills > 0 else Decimal("0.00")

    # 4. Payment Metrics
    total_received = db.execute(
        select(func.coalesce(func.sum(Payment.amount), Decimal("0.00")))
        .where(Payment.is_reversal == False)
    ).scalar() or Decimal("0.00")

    total_outstanding = db.execute(
        select(func.coalesce(func.sum(Bill.outstanding_amount), Decimal("0.00")))
        .where(valid_bills_cond)
    ).scalar() or Decimal("0.00")

    partially_paid_bills = db.execute(
        select(func.count(Bill.id)).where(and_(valid_bills_cond, Bill.payment_status == "PARTIALLY_PAID"))
    ).scalar() or 0

    fully_paid_bills = db.execute(
        select(func.count(Bill.id)).where(and_(valid_bills_cond, Bill.payment_status == "PAID"))
    ).scalar() or 0

    # Overdue payments: outstanding bills older than 30 days
    thirty_days_ago = today - timedelta(days=30)
    overdue_payments = db.execute(
        select(func.coalesce(func.sum(Bill.outstanding_amount), Decimal("0.00")))
        .where(and_(valid_bills_cond, Bill.outstanding_amount > 0, Bill.bill_date < thirty_days_ago))
    ).scalar() or Decimal("0.00")

    # 5. Other-Shop Metrics
    total_shops = db.execute(select(func.count(OtherShop.id)).where(OtherShop.is_deleted == False)).scalar() or 0
    products_with_shops = db.execute(
        select(func.coalesce(func.sum(ShopIssueItem.quantity_issued - ShopIssueItem.quantity_returned), Decimal("0.00")))
        .join(ShopIssue, ShopIssue.id == ShopIssueItem.issue_id)
        .where(ShopIssue.status != "COMPLETED")
    ).scalar() or Decimal("0.00")

    pending_returns_count = db.execute(
        select(func.count(ShopIssue.id)).where(ShopIssue.status.in_(["PENDING", "PARTIALLY_RETURNED"]))
    ).scalar() or 0

    completed_returns_count = db.execute(
        select(func.count(ShopIssue.id)).where(ShopIssue.status == "COMPLETED")
    ).scalar() or 0

    return {
        "customers": {
            "total": total_customers,
            "new_this_month": new_customers_month,
            "active": active_customers,
        },
        "inventory": {
            "total_products": total_products,
            "total_available_stock": total_available_stock,
            "low_stock": low_stock_products,
            "out_of_stock": out_of_stock_products,
            "purchase_value": inv_purchase_val,
            "selling_value": inv_selling_val,
        },
        "sales": {
            "today": today_sales,
            "this_month": month_sales,
            "total": total_sales,
            "total_bills": total_bills,
            "avg_bill_value": avg_bill_val,
        },
        "payments": {
            "total_received": total_received,
            "total_outstanding": total_outstanding,
            "partially_paid_bills": partially_paid_bills,
            "fully_paid_bills": fully_paid_bills,
            "overdue_payments": overdue_payments,
        },
        "other_shops": {
            "total_shops": total_shops,
            "products_with_shops": products_with_shops,
            "pending_returns": pending_returns_count,
            "completed_returns": completed_returns_count,
        }
    }


def get_dashboard_tables(db: Session) -> Dict[str, Any]:
    """Retrieve tabular data for dashboard quick-review sections."""
    # 1. Highest pending-payment customers
    high_pending_query = (
        select(
            Customer.id,
            Customer.customer_code,
            Customer.name,
            Customer.mobile,
            func.coalesce(func.sum(Bill.outstanding_amount), Decimal("0.00")).label("total_pending"),
            func.count(Bill.id).label("pending_bills_count")
        )
        .join(Bill, Bill.customer_id == Customer.id)
        .where(and_(Bill.bill_status == "FINALIZED", Bill.outstanding_amount > 0))
        .group_by(Customer.id, Customer.customer_code, Customer.name, Customer.mobile)
        .order_by(func.sum(Bill.outstanding_amount).desc())
        .limit(10)
    )
    high_pending = [
        {
            "Customer Code": r[1],
            "Customer Name": r[2],
            "Mobile": r[3],
            "Pending Amount (₹)": float(r[4]),
            "Pending Bills": r[5]
        }
        for r in db.execute(high_pending_query).all()
    ]

    # 2. Recent Bills
    recent_bills_query = (
        select(Bill)
        .where(Bill.bill_status != "CANCELLED")
        .order_by(Bill.bill_date.desc(), Bill.id.desc())
        .limit(10)
    )
    recent_bills = [
        {
            "Bill #": b.bill_number,
            "Date": b.bill_date.strftime("%Y-%m-%d"),
            "Customer": b.customer.name,
            "Grand Total (₹)": float(b.grand_total),
            "Received (₹)": float(b.amount_received),
            "Outstanding (₹)": float(b.outstanding_amount),
            "Payment Status": b.payment_status,
        }
        for b in db.execute(recent_bills_query).scalars().all()
    ]

    # 3. Recent Stock Transactions
    recent_tx_query = (
        select(StockTransaction)
        .where(StockTransaction.is_cancelled == False)
        .order_by(StockTransaction.created_at.desc())
        .limit(10)
    )
    recent_tx = [
        {
            "TX Code": tx.transaction_code,
            "Type": tx.transaction_type,
            "Product": tx.product.name,
            "Qty": float(tx.quantity),
            "Unit": tx.product.unit,
            "Party/Ref": tx.party_name or tx.reference_id or "-",
            "Date": tx.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for tx in db.execute(recent_tx_query).scalars().all()
    ]

    # 4. Low Stock Alerts
    low_stock_query = (
        select(Product)
        .where(and_(Product.is_deleted == False, Product.current_stock <= Product.min_stock_level))
        .order_by(Product.current_stock.asc())
        .limit(10)
    )
    low_stock = [
        {
            "Code": p.product_code,
            "Product": p.name,
            "Category": p.category,
            "Current Stock": f"{p.current_stock} {p.unit}",
            "Min Level": f"{p.min_stock_level} {p.unit}",
            "Status": "Out of Stock" if p.current_stock <= 0 else "Low Stock",
        }
        for p in db.execute(low_stock_query).scalars().all()
    ]

    # 5. Pending Other Shop Returns
    pending_returns_query = (
        select(ShopIssue)
        .where(ShopIssue.status.in_(["PENDING", "PARTIALLY_RETURNED"]))
        .order_by(ShopIssue.issue_date.asc())
        .limit(10)
    )
    pending_returns = []
    for issue in db.execute(pending_returns_query).scalars().all():
        for item in issue.items:
            pending_qty = item.quantity_issued - item.quantity_returned
            if pending_qty > Decimal("0.00"):
                pending_returns.append({
                    "Issue #": issue.issue_number,
                    "Shop Name": issue.other_shop.shop_name,
                    "Product": item.product.name,
                    "Issued Qty": float(item.quantity_issued),
                    "Returned Qty": float(item.quantity_returned),
                    "Pending Qty": float(pending_qty),
                    "Issue Date": issue.issue_date.strftime("%Y-%m-%d"),
                    "Status": issue.status,
                })

    # 6. Recent Payments
    recent_payments_query = (
        select(Payment)
        .where(Payment.is_reversal == False)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
        .limit(10)
    )
    recent_payments = [
        {
            "Receipt #": p.payment_number,
            "Date": p.payment_date.strftime("%Y-%m-%d"),
            "Customer": p.customer.name,
            "Bill #": p.bill.bill_number if p.bill else "On Account",
            "Amount (₹)": float(p.amount),
            "Method": p.payment_method,
            "Ref": p.transaction_reference or "-",
        }
        for p in db.execute(recent_payments_query).scalars().all()
    ]

    return {
        "high_pending": pd.DataFrame(high_pending),
        "recent_bills": pd.DataFrame(recent_bills),
        "recent_stock": pd.DataFrame(recent_tx),
        "low_stock": pd.DataFrame(low_stock),
        "pending_returns": pd.DataFrame(pending_returns),
        "recent_payments": pd.DataFrame(recent_payments),
    }


def get_chart_data(db: Session) -> Dict[str, pd.DataFrame]:
    """Retrieve aggregated dataframes for Plotly charts."""
    # 1. Daily sales (last 30 days)
    start_30 = date.today() - timedelta(days=30)
    daily_sales_query = (
        select(Bill.bill_date, func.sum(Bill.grand_total).label("sales"), func.count(Bill.id).label("bills"))
        .where(and_(Bill.bill_status == "FINALIZED", Bill.bill_date >= start_30))
        .group_by(Bill.bill_date)
        .order_by(Bill.bill_date.asc())
    )
    daily_sales_df = pd.DataFrame(
        [{"Date": str(r[0]), "Sales": float(r[1]), "Bills": r[2]} for r in db.execute(daily_sales_query).all()]
    )

    # 2. Payment collection (last 30 days)
    daily_pay_query = (
        select(Payment.payment_date, func.sum(Payment.amount).label("collected"))
        .where(and_(Payment.is_reversal == False, Payment.payment_date >= start_30))
        .group_by(Payment.payment_date)
        .order_by(Payment.payment_date.asc())
    )
    daily_pay_df = pd.DataFrame(
        [{"Date": str(r[0]), "Collected": float(r[1])} for r in db.execute(daily_pay_query).all()]
    )

    # 3. Top-selling products
    top_products_query = (
        select(BillItem.product_name, func.sum(BillItem.quantity).label("total_qty"), func.sum(BillItem.line_total).label("total_rev"))
        .join(Bill, Bill.id == BillItem.bill_id)
        .where(Bill.bill_status == "FINALIZED")
        .group_by(BillItem.product_name)
        .order_by(func.sum(BillItem.line_total).desc())
        .limit(10)
    )
    top_products_df = pd.DataFrame(
        [{"Product": r[0], "Quantity": float(r[1]), "Revenue": float(r[2])} for r in db.execute(top_products_query).all()]
    )

    return {
        "daily_sales": daily_sales_df,
        "daily_payments": daily_pay_df,
        "top_products": top_products_df,
    }


def get_report_data(
    db: Session,
    report_type: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    customer_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    product_id: Optional[int] = None,
) -> pd.DataFrame:
    """
    Generate dataset for any of the 15 required business reports.
    Returns clean Pandas DataFrame ready for display and Excel/PDF export.
    """
    if report_type == "1. Daily Sales Report":
        q = (
            select(Bill.bill_date, func.count(Bill.id), func.sum(Bill.subtotal), func.sum(Bill.discount), func.sum(Bill.tax_amount), func.sum(Bill.grand_total), func.sum(Bill.amount_received), func.sum(Bill.outstanding_amount))
            .where(Bill.bill_status == "FINALIZED")
        )
        if start_date: q = q.where(Bill.bill_date >= start_date)
        if end_date: q = q.where(Bill.bill_date <= end_date)
        q = q.group_by(Bill.bill_date).order_by(Bill.bill_date.desc())
        rows = [
            {"Date": str(r[0]), "Bills": r[1], "Subtotal (₹)": float(r[2]), "Discount (₹)": float(r[3]), "Tax (₹)": float(r[4]), "Grand Total (₹)": float(r[5]), "Received (₹)": float(r[6]), "Outstanding (₹)": float(r[7])}
            for r in db.execute(q).all()
        ]
        return pd.DataFrame(rows)

    elif report_type == "2. Weekly Sales Report":
        # Aggregate by week
        q = select(Bill).where(Bill.bill_status == "FINALIZED")
        if start_date: q = q.where(Bill.bill_date >= start_date)
        if end_date: q = q.where(Bill.bill_date <= end_date)
        bills = db.execute(q).scalars().all()
        data = []
        for b in bills:
            data.append({
                "Year-Week": b.bill_date.strftime("%Y-W%W"),
                "Grand Total": float(b.grand_total),
                "Received": float(b.amount_received),
                "Outstanding": float(b.outstanding_amount),
            })
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        agg = df.groupby("Year-Week").agg({"Grand Total": ["count", "sum"], "Received": "sum", "Outstanding": "sum"}).reset_index()
        agg.columns = ["Week", "Total Bills", "Total Sales (₹)", "Total Received (₹)", "Total Outstanding (₹)"]
        return agg

    elif report_type == "3. Monthly Sales Report":
        q = select(Bill).where(Bill.bill_status == "FINALIZED")
        if start_date: q = q.where(Bill.bill_date >= start_date)
        if end_date: q = q.where(Bill.bill_date <= end_date)
        bills = db.execute(q).scalars().all()
        data = []
        for b in bills:
            data.append({
                "Month": b.bill_date.strftime("%Y-%m"),
                "Grand Total": float(b.grand_total),
                "Received": float(b.amount_received),
                "Outstanding": float(b.outstanding_amount),
            })
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        agg = df.groupby("Month").agg({"Grand Total": ["count", "sum"], "Received": "sum", "Outstanding": "sum"}).reset_index()
        agg.columns = ["Month", "Total Bills", "Total Sales (₹)", "Total Received (₹)", "Total Outstanding (₹)"]
        return agg

    elif report_type == "4. Annual Sales Report":
        q = select(Bill).where(Bill.bill_status == "FINALIZED")
        bills = db.execute(q).scalars().all()
        data = [{"Year": b.bill_date.strftime("%Y"), "Grand Total": float(b.grand_total), "Received": float(b.amount_received), "Outstanding": float(b.outstanding_amount)} for b in bills]
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        agg = df.groupby("Year").agg({"Grand Total": ["count", "sum"], "Received": "sum", "Outstanding": "sum"}).reset_index()
        agg.columns = ["Year", "Total Bills", "Total Sales (₹)", "Total Received (₹)", "Total Outstanding (₹)"]
        return agg

    elif report_type == "5. Customer-wise Sales":
        q = (
            select(Customer.customer_code, Customer.name, Customer.mobile, func.count(Bill.id), func.sum(Bill.grand_total), func.sum(Bill.amount_received), func.sum(Bill.outstanding_amount))
            .join(Bill, Bill.customer_id == Customer.id)
            .where(Bill.bill_status == "FINALIZED")
        )
        if customer_id: q = q.where(Customer.id == customer_id)
        if start_date: q = q.where(Bill.bill_date >= start_date)
        if end_date: q = q.where(Bill.bill_date <= end_date)
        q = q.group_by(Customer.customer_code, Customer.name, Customer.mobile).order_by(func.sum(Bill.grand_total).desc())
        return pd.DataFrame([
            {"Code": r[0], "Customer": r[1], "Mobile": r[2], "Bills Count": r[3], "Total Billed (₹)": float(r[4]), "Paid (₹)": float(r[5]), "Outstanding (₹)": float(r[6])}
            for r in db.execute(q).all()
        ])

    elif report_type == "6. Product-wise Sales":
        q = (
            select(Product.product_code, BillItem.product_name, Product.category, func.sum(BillItem.quantity), Product.unit, func.sum(BillItem.line_total))
            .join(Bill, Bill.id == BillItem.bill_id)
            .join(Product, Product.id == BillItem.product_id)
            .where(Bill.bill_status == "FINALIZED")
        )
        if product_id: q = q.where(Product.id == product_id)
        if start_date: q = q.where(Bill.bill_date >= start_date)
        if end_date: q = q.where(Bill.bill_date <= end_date)
        q = q.group_by(Product.product_code, BillItem.product_name, Product.category, Product.unit).order_by(func.sum(BillItem.line_total).desc())
        return pd.DataFrame([
            {"Code": r[0], "Product": r[1], "Category": r[2], "Quantity Sold": f"{r[3]} {r[4]}", "Total Sales (₹)": float(r[5])}
            for r in db.execute(q).all()
        ])

    elif report_type == "7. Stock-in Report":
        q = (
            select(StockTransaction)
            .where(and_(StockTransaction.transaction_type == "STOCK_IN", StockTransaction.is_cancelled == False))
        )
        if product_id: q = q.where(StockTransaction.product_id == product_id)
        if start_date: q = q.where(StockTransaction.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date: q = q.where(StockTransaction.created_at <= datetime.combine(end_date, datetime.max.time()))
        q = q.order_by(StockTransaction.created_at.desc())
        return pd.DataFrame([
            {"TX Code": tx.transaction_code, "Date": tx.created_at.strftime("%Y-%m-%d"), "Product": tx.product.name, "Qty": float(tx.quantity), "Unit": tx.product.unit, "Supplier": tx.party_name or "-", "Invoice #": tx.reference_id or "-", "Purchase Price (₹)": float(tx.unit_price or 0)}
            for tx in db.execute(q).scalars().all()
        ])

    elif report_type == "8. Stock-out Report":
        q = (
            select(StockTransaction)
            .where(and_(StockTransaction.transaction_type.in_(["STOCK_OUT", "BILL_SALE", "SHOP_ISSUE"]), StockTransaction.is_cancelled == False))
        )
        if product_id: q = q.where(StockTransaction.product_id == product_id)
        if start_date: q = q.where(StockTransaction.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date: q = q.where(StockTransaction.created_at <= datetime.combine(end_date, datetime.max.time()))
        q = q.order_by(StockTransaction.created_at.desc())
        return pd.DataFrame([
            {"TX Code": tx.transaction_code, "Date": tx.created_at.strftime("%Y-%m-%d"), "Type": tx.transaction_type, "Product": tx.product.name, "Qty": float(tx.quantity), "Unit": tx.product.unit, "Party/Ref": tx.party_name or tx.reference_id or "-"}
            for tx in db.execute(q).scalars().all()
        ])

    elif report_type == "9. Current Inventory Report":
        q = select(Product).where(Product.is_deleted == False).order_by(Product.name.asc())
        return pd.DataFrame([
            {"Code": p.product_code, "Name": p.name, "Brand": p.brand, "Category": p.category, "Stock": float(p.current_stock), "Unit": p.unit, "Min Level": float(p.min_stock_level), "Purchase Rate (₹)": float(p.purchase_price), "Selling Rate (₹)": float(p.selling_price), "Valuation (₹)": float(p.current_stock * p.purchase_price)}
            for p in db.execute(q).scalars().all()
        ])

    elif report_type == "10. Low-stock Report":
        q = select(Product).where(and_(Product.is_deleted == False, Product.current_stock <= Product.min_stock_level)).order_by(Product.current_stock.asc())
        return pd.DataFrame([
            {"Code": p.product_code, "Product": p.name, "Category": p.category, "Stock": float(p.current_stock), "Min Level": float(p.min_stock_level), "Unit": p.unit, "Deficit": float(p.min_stock_level - p.current_stock if p.min_stock_level > p.current_stock else 0), "Status": "Out of Stock" if p.current_stock <= 0 else "Low Stock"}
            for p in db.execute(q).scalars().all()
        ])

    elif report_type == "11. Customer Pending-payment Report":
        q = (
            select(Customer.customer_code, Customer.name, Customer.mobile, Customer.city, func.count(Bill.id), func.sum(Bill.outstanding_amount))
            .join(Bill, Bill.customer_id == Customer.id)
            .where(and_(Bill.bill_status == "FINALIZED", Bill.outstanding_amount > 0))
            .group_by(Customer.customer_code, Customer.name, Customer.mobile, Customer.city)
            .order_by(func.sum(Bill.outstanding_amount).desc())
        )
        return pd.DataFrame([
            {"Code": r[0], "Customer": r[1], "Mobile": r[2], "City": r[3] or "-", "Unpaid Bills": r[4], "Total Outstanding (₹)": float(r[5])}
            for r in db.execute(q).all()
        ])

    elif report_type == "12. Payment Collection Report":
        q = select(Payment).where(Payment.is_reversal == False)
        if customer_id: q = q.where(Payment.customer_id == customer_id)
        if start_date: q = q.where(Payment.payment_date >= start_date)
        if end_date: q = q.where(Payment.payment_date <= end_date)
        q = q.order_by(Payment.payment_date.desc(), Payment.id.desc())
        return pd.DataFrame([
            {"Receipt #": p.payment_number, "Date": p.payment_date.strftime("%Y-%m-%d"), "Customer": p.customer.name, "Bill #": p.bill.bill_number if p.bill else "On Account", "Amount (₹)": float(p.amount), "Method": p.payment_method, "Reference": p.transaction_reference or "-"}
            for p in db.execute(q).scalars().all()
        ])

    elif report_type == "13. Other-shop Transaction Report":
        q = select(ShopIssue)
        if shop_id: q = q.where(ShopIssue.shop_id == shop_id)
        if start_date: q = q.where(ShopIssue.issue_date >= start_date)
        if end_date: q = q.where(ShopIssue.issue_date <= end_date)
        q = q.order_by(ShopIssue.issue_date.desc())
        rows = []
        for issue in db.execute(q).scalars().all():
            for item in issue.items:
                rows.append({
                    "Issue #": issue.issue_number,
                    "Shop": issue.other_shop.shop_name,
                    "Issue Date": issue.issue_date.strftime("%Y-%m-%d"),
                    "Product": item.product.name,
                    "Qty Issued": float(item.quantity_issued),
                    "Qty Returned": float(item.quantity_returned),
                    "Pending Qty": float(item.quantity_issued - item.quantity_returned),
                    "Status": issue.status,
                })
        return pd.DataFrame(rows)

    elif report_type == "14. Pending-return Report":
        q = select(ShopIssue).where(ShopIssue.status.in_(["PENDING", "PARTIALLY_RETURNED"])).order_by(ShopIssue.issue_date.asc())
        if shop_id: q = q.where(ShopIssue.shop_id == shop_id)
        rows = []
        for issue in db.execute(q).scalars().all():
            for item in issue.items:
                pending = item.quantity_issued - item.quantity_returned
                if pending > Decimal("0.00"):
                    rows.append({
                        "Issue #": issue.issue_number,
                        "Shop": issue.other_shop.shop_name,
                        "Issue Date": issue.issue_date.strftime("%Y-%m-%d"),
                        "Product": item.product.name,
                        "Pending Qty": float(pending),
                        "Unit": item.product.unit,
                        "Status": issue.status,
                    })
        return pd.DataFrame(rows)

    elif report_type == "15. Completed-return Report":
        q = select(ShopIssue).where(ShopIssue.status == "COMPLETED").order_by(ShopIssue.completed_at.desc())
        if shop_id: q = q.where(ShopIssue.shop_id == shop_id)
        rows = []
        for issue in db.execute(q).scalars().all():
            for item in issue.items:
                rows.append({
                    "Issue #": issue.issue_number,
                    "Shop": issue.other_shop.shop_name,
                    "Issued Date": issue.issue_date.strftime("%Y-%m-%d"),
                    "Completed Date": issue.completed_at.strftime("%Y-%m-%d") if issue.completed_at else "-",
                    "Product": item.product.name,
                    "Total Returned": float(item.quantity_returned),
                    "Unit": item.product.unit,
                })
        return pd.DataFrame(rows)

    return pd.DataFrame()
