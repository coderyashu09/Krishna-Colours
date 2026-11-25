"""
Settings & Administration Page.
Handles Password Changes (initial 1454), User Management (Admin / Staff),
Database Backups & Restore, Business Profile Settings, and Audit Trail Viewer.
"""
from datetime import datetime, date
import os
import streamlit as st
import pandas as pd
from sqlalchemy import select

from config.database import get_db
from config.settings import settings
from database.models import User, BusinessSetting, AuditLog, BackupLog
from components.header import render_header
from components.cards import render_kpi_card
from auth.security import hash_password, verify_password
from auth.login import get_current_user, is_admin
from utils.backup import create_database_backup, restore_database_backup, get_backup_history
from utils.excel_handler import export_dataframe_to_excel


def render_settings_page():
    """Render Settings & System Administration."""
    render_header("System Settings & Administration")
    current_user = get_current_user() or {"id": 1, "username": "admin", "role": "admin"}
    is_admin_user = (current_user.get("role") == "admin")

    tab_pwd, tab_biz, tab_users, tab_backup, tab_audit = st.tabs([
        "🔒 Change Password",
        "🏢 Business Profile",
        "👤 User Management",
        "💾 Database Backups",
        "🛡️ Audit Trail Logs",
    ])

    # 1. CHANGE PASSWORD
    with tab_pwd:
        st.subheader("Change Account Password")
        st.caption("Securely update your login credentials. Password will be hashed using Argon2/bcrypt.")

        with st.form("change_password_form", clear_on_submit=True):
            current_pwd = st.text_input("Current Password *", type="password")
            new_pwd = st.text_input("New Password *", type="password")
            confirm_pwd = st.text_input("Confirm New Password *", type="password")

            submit_pwd = st.form_submit_button("🔑 Update Password", type="primary")

            if submit_pwd:
                if not current_pwd or not new_pwd:
                    st.error("Please fill in all password fields.")
                elif new_pwd != confirm_pwd:
                    st.error("New passwords do not match.")
                elif len(new_pwd) < 4:
                    st.error("Password must be at least 4 characters long.")
                else:
                    with get_db() as db:
                        user_obj = db.execute(select(User).where(User.id == current_user["id"])).scalar_one_or_none()
                        if not user_obj:
                            st.error("User not found.")
                        elif not verify_password(current_pwd, user_obj.password_hash):
                            st.error("Current password verification failed.")
                        else:
                            user_obj.password_hash = hash_password(new_pwd)
                            user_obj.updated_at = datetime.utcnow()
                            st.success("Password changed successfully! Next time you log in, use your new password.")

    # 2. BUSINESS PROFILE
    with tab_biz:
        st.subheader("Business Information & Tax Settings")
        st.caption("Information shown on printed invoices, delivery challans, and customer receipts.")

        if not is_admin_user:
            st.info("Only administrators can modify business profile settings.")
        else:
            with get_db() as db:
                curr_settings = {
                    s.setting_key: s.setting_value
                    for s in db.execute(select(BusinessSetting)).scalars().all()
                }

            with st.form("biz_profile_form"):
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    b_name = st.text_input("Business Name", value=curr_settings.get("shop_name", settings.APP_NAME))
                    b_phone = st.text_input("Phone Number", value=curr_settings.get("shop_phone", settings.APP_PHONE))
                    b_gstin = st.text_input("GSTIN Number", value=curr_settings.get("shop_gstin", settings.APP_GSTIN))
                with col_b2:
                    b_tagline = st.text_input("Tagline / Dealership Notice", value=curr_settings.get("shop_tagline", settings.APP_TAGLINE))
                    b_state = st.text_input("State & State Code", value=curr_settings.get("shop_state", settings.APP_STATE))
                    b_prefix = st.text_input("Bill Prefix", value=curr_settings.get("bill_prefix", "KC-"))

                b_addr = st.text_input("Address", value=curr_settings.get("shop_address", settings.APP_ADDRESS))
                b_terms = st.text_area("Invoice Terms & Conditions", value=curr_settings.get("invoice_terms", ""))

                save_biz = st.form_submit_button("💾 Save Business Settings", type="primary")

                if save_biz:
                    with get_db() as db:
                        updates = {
                            "shop_name": b_name,
                            "shop_tagline": b_tagline,
                            "shop_phone": b_phone,
                            "shop_address": b_addr,
                            "shop_gstin": b_gstin,
                            "shop_state": b_state,
                            "bill_prefix": b_prefix,
                            "invoice_terms": b_terms,
                        }
                        for k, v in updates.items():
                            s_obj = db.execute(select(BusinessSetting).where(BusinessSetting.setting_key == k)).scalar_one_or_none()
                            if s_obj:
                                s_obj.setting_value = v
                                s_obj.updated_at = datetime.utcnow()
                            else:
                                db.add(BusinessSetting(setting_key=k, setting_value=v))
                    st.success("Business profile settings saved!")
                    st.rerun()

    # 3. USER MANAGEMENT
    with tab_users:
        st.subheader("User Accounts & Role Permissions")
        st.caption("Manage staff and administrator login accounts.")

        if not is_admin_user:
            st.info("User management is restricted to Administrators.")
        else:
            with get_db() as db:
                users_list = db.execute(select(User).order_by(User.id.asc())).scalars().all()

            u_rows = [
                {
                    "ID": u.id,
                    "Username": u.username,
                    "Full Name": u.full_name,
                    "Role": u.role.upper(),
                    "Active": "Active" if u.is_active else "Deactivated",
                    "Created Date": u.created_at.strftime("%Y-%m-%d"),
                }
                for u in users_list
            ]
            st.dataframe(pd.DataFrame(u_rows), use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("##### ➕ Create New Staff or Admin Account")
            with st.form("create_user_form", clear_on_submit=True):
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    new_uname = st.text_input("Username *", placeholder="e.g. staff1")
                    new_fname = st.text_input("Full Name *", placeholder="e.g. Mukesh Sharma")
                with col_u2:
                    new_upwd = st.text_input("Initial Password *", type="password")
                    new_urole = st.selectbox("Role *", options=["staff", "admin"], format_func=lambda x: "👤 Staff Member" if x == "staff" else "👑 Administrator")

                create_u_btn = st.form_submit_button("Create User Account", type="primary")

                if create_u_btn:
                    if not new_uname.strip() or not new_upwd.strip():
                        st.error("Username and initial password are required.")
                    else:
                        with get_db() as db:
                            exist_u = db.execute(select(User).where(User.username == new_uname.strip())).scalar_one_or_none()
                            if exist_u:
                                st.error(f"Username '{new_uname}' already exists.")
                            else:
                                new_u = User(
                                    username=new_uname.strip(),
                                    password_hash=hash_password(new_upwd.strip()),
                                    full_name=new_fname.strip() or new_uname.strip(),
                                    role=new_urole,
                                    is_active=True,
                                )
                                db.add(new_u)
                                st.success(f"User account '{new_u.username}' created successfully!")
                                st.rerun()

    # 4. DATABASE BACKUP & RESTORE
    with tab_backup:
        st.subheader("Database Backup & Disaster Recovery")
        st.caption("Protect company data with automated backups, downloads, and verified restore procedures.")

        if not is_admin_user:
            st.warning("Database backup and restore is restricted to Administrators.")
        else:
            col_b1, col_b2 = st.columns([2, 1])
            with col_b1:
                st.markdown("##### Create New Backup")
                backup_notes = st.text_input("Backup Description / Label", placeholder="e.g. Monthly closing backup or Pre-update snapshot")
                if st.button("💾 Trigger Manual Backup Now", type="primary"):
                    with get_db() as db:
                        success, msg, path = create_database_backup(
                            db=db,
                            backup_type="MANUAL",
                            user_id=current_user.get("id"),
                            username=current_user.get("username", "admin"),
                            notes=backup_notes,
                        )
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

            with col_b2:
                st.markdown("##### Storage Location")
                st.code(str(settings.BACKUP_DIR))

            st.markdown("---")
            st.markdown("##### Backup History & Downloads")
            with get_db() as db:
                backups = get_backup_history(db)

            if not backups:
                st.info("No backups created yet.")
            else:
                b_rows = [
                    {
                        "ID": b.id,
                        "Filename": b.filename,
                        "Size (KB)": f"{b.file_size_bytes / 1024:.1f}",
                        "Type": b.backup_type,
                        "Status": b.status,
                        "Created At": b.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "Notes": b.notes or "",
                    }
                    for b in backups
                ]
                st.dataframe(pd.DataFrame(b_rows), use_container_width=True, hide_index=True)

                # Download selected backup
                valid_backups = [b for b in backups if b.status == "SUCCESS"]
                if valid_backups:
                    bk_choice = st.selectbox("Select Backup to Download or Restore", options=[b.filename for b in valid_backups])
                    target_file = settings.BACKUP_DIR / bk_choice

                    if target_file.exists():
                        with open(target_file, "rb") as bf:
                            file_data = bf.read()
                        st.download_button(
                            label=f"📥 Download Selected Backup ({bk_choice})",
                            data=file_data,
                            file_name=bk_choice,
                            mime="application/gzip",
                        )

                        # Restore section
                        st.markdown("---")
                        st.markdown("##### 🚨 Restore Database from Backup")
                        st.warning("CAUTION: Restoring will overwrite the current database with data from the backup file. This cannot be undone.")
                        confirm_text = st.text_input("To confirm restore, type 'RESTORE DATABASE' exactly:")
                        if st.button("⚠️ RESTORE DATABASE NOW", type="secondary"):
                            with get_db() as db:
                                res_ok, res_msg = restore_database_backup(
                                    db=db,
                                    backup_filename=bk_choice,
                                    confirmation_text=confirm_text,
                                    user_id=current_user.get("id"),
                                    username=current_user.get("username", "admin"),
                                )
                            if res_ok:
                                st.success(res_msg)
                            else:
                                st.error(res_msg)

    # 5. AUDIT TRAIL LOGS
    with tab_audit:
        st.subheader("Security & Operational Audit Trail")
        st.caption("Immutable record of critical business activities: sales, reversals, logins, price updates, and cancellations.")

        if not is_admin_user:
            st.info("Audit logs are accessible to Administrators only.")
        else:
            with get_db() as db:
                logs_query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)
                logs = list(db.execute(logs_query).scalars().all())

            if not logs:
                st.info("No audit logs recorded yet.")
            else:
                log_data = [
                    {
                        "Timestamp": l.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "User": l.username,
                        "Action": l.action,
                        "Record Type": l.record_type,
                        "Record ID": l.record_id or "-",
                        "Details": l.details or "-",
                    }
                    for l in logs
                ]
                df_logs = pd.DataFrame(log_data)
                st.dataframe(df_logs, use_container_width=True, hide_index=True)

                exp_log_bytes = export_dataframe_to_excel(df_logs, sheet_name="Audit Logs", title="Krishna Colour - Security & Audit Trail")
                st.download_button(
                    "📥 Export Audit Logs (Excel)",
                    data=exp_log_bytes,
                    file_name=f"krishna_colour_audit_logs_{date.today().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
