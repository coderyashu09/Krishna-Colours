"""
Master Test Runner.
Executes all test suites and reports full status.
"""
import sys
import os

# Add root folder to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_auth import (
    test_password_hashing, test_initial_admin_authentication,
    test_role_permissions, test_rate_limiting
)
from tests.test_inventory import test_product_crud_and_stock_flow
from tests.test_billing import test_billing_multi_item_and_inventory_lifecycle
from tests.test_payments import test_payment_tracking_and_overpayment_prevention
from tests.test_returns import test_other_shop_and_partial_returns_flow
from tests.test_reports import test_dashboard_metrics_and_charts, test_all_fifteen_reports


def run_all():
    print("=" * 60)
    print("KRISHNA COLOUR – ASIAN PAINTS MANAGEMENT SYSTEM")
    print("COMPREHENSIVE AUTOMATED TEST SUITE")
    print("=" * 60)

    test_steps = [
        ("Authentication & Security", [
            test_password_hashing,
            test_initial_admin_authentication,
            test_role_permissions,
            test_rate_limiting,
        ]),
        ("Inventory & Stock Management", [
            test_product_crud_and_stock_flow,
        ]),
        ("Billing & POS Lifecycle", [
            test_billing_multi_item_and_inventory_lifecycle,
        ]),
        ("Payments & Overpayment Prevention", [
            test_payment_tracking_and_overpayment_prevention,
        ]),
        ("Other Shops & Return Management", [
            test_other_shop_and_partial_returns_flow,
        ]),
        ("Reports & Analytics (All 15 Reports)", [
            test_dashboard_metrics_and_charts,
            test_all_fifteen_reports,
        ]),
    ]

    total_passed = 0
    total_tests = 0

    for suite_name, funcs in test_steps:
        print(f"\n[RUNNING] Suite: {suite_name}")
        for fn in funcs:
            total_tests += 1
            try:
                fn()
                print(f"  ✓ {fn.__name__} PASSED")
                total_passed += 1
            except Exception as e:
                print(f"  ✗ {fn.__name__} FAILED: {str(e)}")
                raise

    print("\n" + "=" * 60)
    print(f"TEST RESULTS: {total_passed} / {total_tests} SUITES PASSED (100% SUCCESS)")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
