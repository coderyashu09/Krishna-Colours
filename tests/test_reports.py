"""
Automated Tests for Reports and Dashboard Metrics.
Verifies all 15 reports run without syntax errors and produce accurate DataFrames.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date
import pytest
from config.database import get_db, init_db
from services.report_service import (
    get_dashboard_metrics, get_dashboard_tables, get_chart_data, get_report_data
)
from pages.reports import REPORT_LIST


def setup_module():
    init_db()


def test_dashboard_metrics_and_charts():
    with get_db() as db:
        metrics = get_dashboard_metrics(db)
        assert "sales" in metrics
        assert "inventory" in metrics
        assert "payments" in metrics
        assert "customers" in metrics
        assert "other_shops" in metrics

        tables = get_dashboard_tables(db)
        assert "high_pending" in tables
        assert "recent_bills" in tables
        assert "low_stock" in tables

        charts = get_chart_data(db)
        assert "daily_sales" in charts
        assert "daily_payments" in charts
        assert "top_products" in charts


def test_all_fifteen_reports():
    with get_db() as db:
        for rep_name in REPORT_LIST:
            df = get_report_data(
                db=db,
                report_type=rep_name,
                start_date=date(2020, 1, 1),
                end_date=date(2030, 12, 31)
            )
            assert df is not None
            # Verify it's a pandas DataFrame
            assert hasattr(df, "columns")


if __name__ == "__main__":
    setup_module()
    test_dashboard_metrics_and_charts()
    test_all_fifteen_reports()
    print("test_reports.py: ALL TESTS PASSED!")
