"""
Master Test Runner for Krishna Colour – Asian Paints Customer Management System.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_auth import (
    setup_module as auth_setup,
    test_password_hashing,
    test_initial_admin_authentication,
    test_role_permissions,
    test_rate_limiting,
)
from tests.test_customer_management import (
    test_initial_asian_paints_dropdown_catalog,
    test_bargaining_final_deal_and_payment_cases,
    test_duplicate_prevention_search_and_editing,
    test_admin_item_management_and_history_preservation,
)
from tests.test_ui_e2e import test_full_ui_end_to_end_flow


def run_all():
    print("=" * 64)
    print("KRISHNA COLOUR – ASIAN PAINTS CUSTOMER MANAGEMENT SYSTEM")
    print("AUTOMATED VERIFICATION TEST SUITE")
    print("=" * 64)

    auth_setup()

    suites = [
        ("Authentication & Security", [
            test_password_hashing,
            test_initial_admin_authentication,
            test_role_permissions,
            test_rate_limiting,
        ]),
        ("Customer Management, Multi-Bill, Bargaining & Admin Items", [
            test_initial_asian_paints_dropdown_catalog,
            test_bargaining_final_deal_and_payment_cases,
            test_duplicate_prevention_search_and_editing,
            test_admin_item_management_and_history_preservation,
        ]),
        ("End-to-End Streamlit UI Flow", [
            test_full_ui_end_to_end_flow,
        ]),
    ]

    passed = 0
    total = 0
    for name, funcs in suites:
        print(f"\n[RUNNING] {name}")
        for fn in funcs:
            total += 1
            fn()
            print(f"  ✓ {fn.__name__} PASSED")
            passed += 1

    print("\n" + "=" * 64)
    print(f"TEST RESULTS: {passed} / {total} PASSED (100% SUCCESS)")
    print("=" * 64)


if __name__ == "__main__":
    run_all()
