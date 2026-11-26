"""
End-to-End Streamlit UI Verification Test using streamlit.testing.v1.AppTest.
Executes in a fresh subprocess with an isolated temporary SQLite database
so production data in krishna_colour.db is never modified.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path


_E2E_SCRIPT = r"""
import os
import sys
from pathlib import Path
import streamlit.testing.v1.element_tree as et
from streamlit.testing.v1 import AppTest

sys.path.insert(0, os.getcwd())

# Guard against Streamlit 1.57.0 AppTest omission on Dataframe._widget_state
_orig_get_widget_state = et.get_widget_state
def _safe_get_widget_state(node):
    try:
        return _orig_get_widget_state(node)
    except (AttributeError, KeyError):
        return None
et.get_widget_state = _safe_get_widget_state

at = AppTest.from_file("app.py", default_timeout=20)
at.run()
assert not at.exception

# 1. Wrong password rejected, valid password 1454 succeeds
at.text_input[0].set_value("admin")
at.text_input[1].set_value("wrong")
at.button[0].click().run()
assert len(at.error) == 1

at.text_input[0].set_value("admin")
at.text_input[1].set_value("1454")
at.button[0].click().run()
assert not at.exception

# 2. Add Customer with Bill #244 (Option A + Option B items) and Bill #12540
at.radio(key="nav_selection_radio").set_value("Add Customer").run()
at.text_input(key="nc_name_0").set_value("Rahul Patel")
at.text_input(key="nc_mobile_0").set_value("9876543210")
at.text_area(key="nc_address_0").set_value("Rajkot")
at.text_input(key="nc_bill_no_0").set_value("244")

at.button(key="nc_item_0_add_a").click().run()
assert len(at.session_state["new_bill_items_draft"]) == 1

at.radio(key="nc_item_0_mode").set_value("Option B: Custom Item Textbox").run()
at.text_input(key="nc_item_0_custom_name").set_value("Wall putty")
at.text_input(key="nc_item_0_custom_size").set_value("5 kg")
at.button(key="nc_item_0_add_b").click().run()
assert len(at.session_state["new_bill_items_draft"]) == 2

at.number_input(key="nc_deal_amt_0").set_value(250.0)
at.number_input(key="nc_rec_amt_0").set_value(150.0)
at.checkbox(key="nc_has_pending_0").set_value(True).run()

at.button(key="nc_queue_bill_btn").click().run()
assert len(at.session_state["new_cust_bills_queue"]) == 1
assert at.text_input(key="nc_bill_no_1").value == ""
assert at.number_input(key="nc_deal_amt_1").value == 0.0

# Bill #12540 without pending checked: Final Deal 600, Received 500 -> Closed at ₹500 (no pending!)
at.text_input(key="nc_bill_no_1").set_value("12540")
at.number_input(key="nc_deal_amt_1").set_value(600.0)
at.number_input(key="nc_rec_amt_1").set_value(500.0)
at.button(key="nc_save_all").click().run()

assert not at.exception
assert at.session_state["current_page"] == "Customers"
assert at.session_state["selected_customer_id"] == 1

# 3. Dashboard shows ONLY Bill #244 pending (Bill #12540 has no pending!)
at.radio(key="nav_selection_radio").set_value("Dashboard").run()
assert not at.exception
assert len(at.dataframe) == 1
df_pend = at.dataframe[0].value
assert len(df_pend) == 1
assert df_pend.iloc[0]["Bill Number(s)"] == "244"
assert "Original Amount" not in df_pend.columns
assert df_pend.iloc[0]["Final Deal Amount"] == "₹250.00"
assert df_pend.iloc[0]["Pending Amount"] == "₹100.00"

# 4. Open Customer Profile from Dashboard and pay remaining ₹100
at.button(key="dash_quick_open_btn").click().run()
assert not at.exception
assert at.session_state["current_page"] == "Customers"
pay_btns = [b for b in at.button if "Record Payment" in b.label]
assert len(pay_btns) == 1
pay_btns[0].click().run()
assert not at.exception

# 5. Back to Dashboard -> Pending table is cleared cleanly
at.radio(key="nav_selection_radio").set_value("Dashboard").run()
assert not at.exception
assert len(at.dataframe) == 0
assert any("All customer bills are fully paid" in s.value for s in at.success)

# 6. Customers Search by Bill Number 12540 & Admin Settings rendering
at.session_state["selected_customer_id"] = None
at.radio(key="nav_selection_radio").set_value("Customers").run()
at.text_input(key="cust_list_search").set_value("12540").run()
assert len(at.dataframe[0].value) == 1
assert at.dataframe[0].value.iloc[0]["Customer Name"] == "Rahul Patel"

at.radio(key="nav_selection_radio").set_value("Admin Settings").run()
assert not at.exception
print("UI E2E PASSED")
"""


def test_full_ui_end_to_end_flow():
    root_dir = Path(__file__).resolve().parent.parent
    tmp_db = Path(tempfile.gettempdir()) / "kc_ui_e2e_isolated.db"
    if tmp_db.exists():
        tmp_db.unlink()

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_db}"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.run(
            [sys.executable, "-c", _E2E_SCRIPT],
            cwd=str(root_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert proc.returncode == 0, f"E2E UI test failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        assert "UI E2E PASSED" in proc.stdout
    finally:
        if tmp_db.exists():
            try:
                tmp_db.unlink()
            except Exception:
                pass
