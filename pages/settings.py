"""
Admin Settings Page for Krishna Colour – Asian Paints Customer Management System.
Provides:
1. Dropdown Item Management (Categories, Products, Pack Sizes) backed by database
   with archive/deactivate protection to preserve historical customer records.
2. Security & Password Management (Argon2/bcrypt).
3. Database Backup, Restore, and Audit Trail.
"""
from datetime import date, datetime
import pandas as pd
import streamlit as st
from sqlalchemy import select

from config.database import get_db
from config.settings import settings
from database.models import User, AuditLog
from components.header import render_header
from auth.login import get_current_user
from auth.security import hash_password, verify_password
from services.item_service import (
    get_categories,
    get_products_for_category,
    get_pack_sizes_for_product,
    add_category,
    rename_category,
    is_category_used_in_bills,
    delete_or_archive_category,
    add_product,
    rename_product,
    is_product_used_in_bills,
    remove_or_archive_product,
    reactivate_product,
    add_pack_size,
    rename_pack_size,
    remove_or_archive_pack_size,
)
from utils.backup import create_database_backup, restore_database_backup, get_backup_history


def render_settings_page():
    """Render Admin Settings interface."""
    render_header("Admin Settings")
    current_user = get_current_user() or {"id": 1, "username": "admin", "role": "admin"}
    username = current_user.get("username", "admin")

    tab_items, tab_pwd, tab_backup = st.tabs([
        "🎨 Manage Dropdown Items",
        "🔒 Security & Users",
        "💾 Backups & Audit Log",
    ])

    # 1. DROPDOWN ITEM MANAGEMENT
    with tab_items:
        st.subheader("Dropdown Item Management")
        st.caption(
            "Add, rename, or deactivate Categories, Products, and Pack Sizes. "
            "Changes immediately update the customer entry dropdown while preserving historical customer records."
        )

        # A. CATEGORIES
        with st.expander("1. Manage Categories", expanded=True):
            with get_db() as db:
                all_cats = get_categories(db, include_inactive=True)
                cat_snapshot = [{"id": c.id, "name": c.name, "is_active": c.is_active} for c in all_cats]

            col_ac1, col_ac2 = st.columns([2, 1])
            with col_ac1:
                new_cat_name = st.text_input("New Category Name", placeholder="e.g. Wood & Metal Finishes", key="adm_new_cat")
            with col_ac2:
                st.write("")
                st.write("")
                if st.button("➕ Add Category", type="primary", use_container_width=True, key="adm_add_cat_btn"):
                    try:
                        with get_db() as db:
                            add_category(db, new_cat_name, username=username)
                        st.success(f"Category '{new_cat_name.strip()}' added!")
                        st.rerun()
                    except ValueError as ve:
                        st.error(str(ve))

            if cat_snapshot:
                cat_opts = {
                    f"{c['name']} {'(Archived)' if not c['is_active'] else ''}": c
                    for c in cat_snapshot
                }
                sel_cat_lbl = st.selectbox("Select Category to Rename or Delete", options=list(cat_opts.keys()), key="adm_edit_cat_sel")
                sel_cat = cat_opts[sel_cat_lbl]

                col_rc1, col_rc2, col_dc = st.columns([2, 1, 1.2])
                with col_rc1:
                    ren_cat_val = st.text_input("Category Name", value=sel_cat["name"], key=f"adm_ren_cat_{sel_cat['id']}")
                with col_rc2:
                    st.write("")
                    st.write("")
                    if st.button("💾 Rename", key=f"adm_ren_cat_btn_{sel_cat['id']}", use_container_width=True):
                        try:
                            with get_db() as db:
                                rename_category(db, sel_cat["id"], ren_cat_val, username=username)
                            st.success("Category renamed!")
                            st.rerun()
                        except ValueError as ve:
                            st.error(str(ve))
                with col_dc:
                    with get_db() as db:
                        used_cnt = is_category_used_in_bills(db, sel_cat["id"])
                    btn_lbl = "🗄️ Archive Category" if used_cnt > 0 else "🗑️ Delete Category"
                    st.write("")
                    st.write("")
                    if st.button(btn_lbl, key=f"adm_del_cat_btn_{sel_cat['id']}", use_container_width=True):
                        with get_db() as db:
                            _, msg = delete_or_archive_category(db, sel_cat["id"], archive_if_used=True, username=username)
                        st.success(msg)
                        st.rerun()

        # B. PRODUCTS
        with st.expander("2. Manage Products", expanded=True):
            with get_db() as db:
                active_cats = get_categories(db, include_inactive=False)
                active_cat_map = {c.name: c.id for c in active_cats}

            if not active_cat_map:
                st.warning("Create an active category first.")
            else:
                sel_pcat_name = st.selectbox("Select Category", options=list(active_cat_map.keys()), key="adm_prod_cat_sel")
                sel_pcat_id = active_cat_map[sel_pcat_name]

                col_ap1, col_ap2, col_ap3 = st.columns([1.8, 1.8, 1])
                with col_ap1:
                    new_prod_name = st.text_input("New Product Name", placeholder="e.g. Royale Aspira", key="adm_new_prod")
                with col_ap2:
                    new_prod_sizes = st.text_input("Initial Pack Sizes (comma-separated)", value="1 L, 4 L, 10 L, 20 L", key="adm_new_prod_sizes")
                with col_ap3:
                    st.write("")
                    st.write("")
                    if st.button("➕ Add Product", type="primary", use_container_width=True, key="adm_add_prod_btn"):
                        try:
                            sizes_list = [s.strip() for s in new_prod_sizes.split(",") if s.strip()]
                            with get_db() as db:
                                add_product(db, sel_pcat_id, new_prod_name, pack_sizes=sizes_list, username=username)
                            st.success(f"Product '{new_prod_name.strip()}' added to '{sel_pcat_name}'!")
                            st.rerun()
                        except ValueError as ve:
                            st.error(str(ve))

                with get_db() as db:
                    prods = get_products_for_category(db, sel_pcat_id, include_inactive=True)
                    prods_snap = [
                        {
                            "id": p.id,
                            "name": p.name,
                            "is_active": p.is_active,
                            "used_count": is_product_used_in_bills(db, p.id),
                        }
                        for p in prods
                    ]

                if not prods_snap:
                    st.info("No products under this category yet.")
                else:
                    p_opts = {
                        f"{p['name']} {'(Archived)' if not p['is_active'] else ''}": p
                        for p in prods_snap
                    }
                    sel_p_lbl = st.selectbox("Select Product to Edit / Remove", options=list(p_opts.keys()), key="adm_edit_prod_sel")
                    sel_p = p_opts[sel_p_lbl]

                    col_ep1, col_ep2 = st.columns([2, 1])
                    with col_ep1:
                        ren_prod_val = st.text_input("Edit Product Name", value=sel_p["name"], key=f"adm_ren_prod_{sel_p['id']}")
                    with col_ep2:
                        st.write("")
                        st.write("")
                        if st.button("💾 Update Name", key=f"adm_ren_prod_btn_{sel_p['id']}", use_container_width=True):
                            try:
                                with get_db() as db:
                                    rename_product(db, sel_p["id"], ren_prod_val, username=username)
                                st.success("Product name updated! Existing customer records remain intact.")
                                st.rerun()
                            except ValueError as ve:
                                st.error(str(ve))

                    if sel_p["is_active"]:
                        if sel_p["used_count"] > 0:
                            st.warning(
                                f"⚠️ '{sel_p['name']}' is already used in **{sel_p['used_count']}** historical customer bill item(s). "
                                "Archiving removes it from dropdowns while preserving customer history."
                            )
                            confirm_arch = st.checkbox(f"Confirm archive/deactivate '{sel_p['name']}'", key=f"adm_chk_arch_{sel_p['id']}")
                            if st.button("🗄️ Archive / Deactivate Product", key=f"adm_arch_btn_{sel_p['id']}", disabled=not confirm_arch):
                                with get_db() as db:
                                    _, msg = remove_or_archive_product(db, sel_p["id"], archive_only=True, username=username)
                                st.success(msg)
                                st.rerun()
                        else:
                            col_del1, col_del2 = st.columns(2)
                            with col_del1:
                                if st.button("🗄️ Deactivate (Hide from Dropdown)", key=f"adm_deact_btn_{sel_p['id']}", use_container_width=True):
                                    with get_db() as db:
                                        _, msg = remove_or_archive_product(db, sel_p["id"], archive_only=True, username=username)
                                    st.success(msg)
                                    st.rerun()
                            with col_del2:
                                confirm_perm = st.checkbox(f"Confirm permanent delete of unused '{sel_p['name']}'", key=f"adm_chk_del_{sel_p['id']}")
                                if st.button("🗑️ Delete Permanently", key=f"adm_perm_del_{sel_p['id']}", use_container_width=True, disabled=not confirm_perm):
                                    with get_db() as db:
                                        _, msg = remove_or_archive_product(db, sel_p["id"], archive_only=False, username=username)
                                    st.success(msg)
                                    st.rerun()
                    else:
                        if st.button(f"♻️ Reactivate '{sel_p['name']}'", key=f"adm_react_btn_{sel_p['id']}"):
                            with get_db() as db:
                                reactivate_product(db, sel_p["id"], username=username)
                            st.success(f"'{sel_p['name']}' is active again!")
                            st.rerun()

        # C. PACK SIZES
        with st.expander("3. Manage Pack Sizes", expanded=True):
            with get_db() as db:
                cats_ps = get_categories(db, include_inactive=False)
                cat_ps_map = {c.name: c.id for c in cats_ps}

            if cat_ps_map:
                col_psc, col_psp = st.columns(2)
                with col_psc:
                    sel_psc_name = st.selectbox("Category", options=list(cat_ps_map.keys()), key="adm_ps_cat_sel")
                with get_db() as db:
                    ps_prods = get_products_for_category(db, cat_ps_map[sel_psc_name], include_inactive=False)
                    ps_prod_map = {p.name: p.id for p in ps_prods}

                with col_psp:
                    if ps_prod_map:
                        sel_psp_name = st.selectbox("Product", options=list(ps_prod_map.keys()), key="adm_ps_prod_sel")
                        sel_psp_id = ps_prod_map[sel_psp_name]
                    else:
                        sel_psp_id = None
                        st.info("No active products in this category.")

                if sel_psp_id:
                    col_aps1, col_aps2 = st.columns([2, 1])
                    with col_aps1:
                        new_ps_lbl = st.text_input("Add Pack Size", placeholder="e.g. 500 ml, 5 L, 25 L", key="adm_new_ps_lbl")
                    with col_aps2:
                        st.write("")
                        st.write("")
                        if st.button("➕ Add Pack Size", use_container_width=True, key="adm_add_ps_btn"):
                            try:
                                with get_db() as db:
                                    add_pack_size(db, sel_psp_id, new_ps_lbl, username=username)
                                st.success(f"Pack size '{new_ps_lbl.strip()}' added!")
                                st.rerun()
                            except ValueError as ve:
                                st.error(str(ve))

                    with get_db() as db:
                        curr_sizes = get_pack_sizes_for_product(db, sel_psp_id, include_inactive=False)
                        sizes_snap = [{"id": s.id, "label": s.size_label} for s in curr_sizes]

                    if sizes_snap:
                        ps_opts = {s["label"]: s for s in sizes_snap}
                        sel_s_lbl = st.selectbox("Select Pack Size to Edit / Remove", options=list(ps_opts.keys()), key="adm_edit_ps_sel")
                        sel_s = ps_opts[sel_s_lbl]

                        col_es1, col_es2, col_es3 = st.columns([2, 1, 1])
                        with col_es1:
                            ren_ps_val = st.text_input("Pack Size Label", value=sel_s["label"], key=f"adm_ren_ps_{sel_s['id']}")
                        with col_es2:
                            st.write("")
                            st.write("")
                            if st.button("💾 Update", key=f"adm_ren_ps_btn_{sel_s['id']}", use_container_width=True):
                                try:
                                    with get_db() as db:
                                        rename_pack_size(db, sel_s["id"], ren_ps_val, username=username)
                                    st.success("Pack size updated!")
                                    st.rerun()
                                except ValueError as ve:
                                    st.error(str(ve))
                        with col_es3:
                            st.write("")
                            st.write("")
                            if st.button("🗑️ Remove", key=f"adm_del_ps_btn_{sel_s['id']}", use_container_width=True):
                                with get_db() as db:
                                    _, msg = remove_or_archive_pack_size(db, sel_s["id"], username=username)
                                st.success(msg)
                                st.rerun()

    # 2. SECURITY & USERS
    with tab_pwd:
        st.subheader("Change Password")
        with st.form("change_password_form", clear_on_submit=True):
            curr_p = st.text_input("Current Password *", type="password")
            new_p = st.text_input("New Password *", type="password")
            conf_p = st.text_input("Confirm New Password *", type="password")

            if st.form_submit_button("🔑 Update Password", type="primary"):
                if not curr_p or not new_p:
                    st.error("Please fill all password fields.")
                elif new_p != conf_p:
                    st.error("New passwords do not match.")
                elif len(new_p) < 4:
                    st.error("Password must be at least 4 characters.")
                else:
                    with get_db() as db:
                        u_obj = db.get(User, current_user["id"])
                        if not u_obj or not verify_password(curr_p, u_obj.password_hash):
                            st.error("Current password is incorrect.")
                        else:
                            u_obj.password_hash = hash_password(new_p)
                            u_obj.updated_at = datetime.utcnow()
                            st.success("Password updated successfully!")

        st.markdown("---")
        st.subheader("Authorized Users")
        with get_db() as db:
            users = db.execute(select(User).order_by(User.id.asc())).scalars().all()
            u_rows = [
                {
                    "Username": u.username,
                    "Full Name": u.full_name,
                    "Role": u.role.upper(),
                    "Status": "Active" if u.is_active else "Inactive",
                }
                for u in users
            ]
        st.dataframe(pd.DataFrame(u_rows), use_container_width=True, hide_index=True)

        with st.form("create_staff_user_form", clear_on_submit=True):
            st.markdown("##### Add Authorized User")
            cu1, cu2 = st.columns(2)
            with cu1:
                nu_name = st.text_input("Username *", placeholder="e.g. staff1")
                nu_full = st.text_input("Full Name *", placeholder="e.g. Suresh Patel")
            with cu2:
                nu_pwd = st.text_input("Password *", type="password")
                nu_role = st.selectbox("Role", options=["staff", "admin"])

            if st.form_submit_button("➕ Create User"):
                if not nu_name.strip() or not nu_full.strip() or len(nu_pwd) < 4:
                    st.error("Provide username, full name, and password (min 4 characters).")
                else:
                    with get_db() as db:
                        exists = db.execute(select(User).where(User.username == nu_name.strip())).scalar_one_or_none()
                        if exists:
                            st.error("Username already exists.")
                        else:
                            db.add(
                                User(
                                    username=nu_name.strip(),
                                    full_name=nu_full.strip(),
                                    password_hash=hash_password(nu_pwd),
                                    role=nu_role,
                                    is_active=True,
                                )
                            )
                            st.success(f"User '{nu_name.strip()}' created!")
                            st.rerun()

    # 3. BACKUPS & AUDIT LOG
    with tab_backup:
        st.subheader("Database Backups")
        if st.button("💾 Create Backup Now", type="primary"):
            with get_db() as db:
                ok, msg, _ = create_database_backup(
                    db=db,
                    backup_type="MANUAL",
                    user_id=current_user.get("id"),
                    username=username,
                )
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

        with get_db() as db:
            backups = get_backup_history(db)
            b_rows = [
                {
                    "Filename": b.filename,
                    "Size (KB)": f"{b.file_size_bytes / 1024:.1f}",
                    "Status": b.status,
                    "Created At": b.created_at.strftime("%Y-%m-%d %H:%M"),
                }
                for b in backups
            ]

        if b_rows:
            st.dataframe(pd.DataFrame(b_rows), use_container_width=True, hide_index=True)
            valid_b = [b["Filename"] for b in b_rows if b["Status"] == "SUCCESS"]
            if valid_b:
                chosen_b = st.selectbox("Select Backup", options=valid_b)
                b_path = settings.BACKUP_DIR / chosen_b
                if b_path.exists():
                    with open(b_path, "rb") as f:
                        st.download_button(
                            f"📥 Download {chosen_b}",
                            data=f.read(),
                            file_name=chosen_b,
                            mime="application/gzip",
                        )
                    confirm_rst = st.text_input("Type 'RESTORE DATABASE' to restore selected backup:")
                    if st.button("⚠️ Restore Backup"):
                        with get_db() as db:
                            r_ok, r_msg = restore_database_backup(
                                db, chosen_b, confirm_rst, user_id=current_user.get("id"), username=username
                            )
                        if r_ok:
                            st.success(r_msg)
                        else:
                            st.error(r_msg)

        st.markdown("---")
        st.subheader("Recent Audit Trail")
        with get_db() as db:
            logs = db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)).scalars().all()
            l_rows = [
                {
                    "Time": l.created_at.strftime("%Y-%m-%d %H:%M"),
                    "User": l.username,
                    "Action": l.action,
                    "Record": f"{l.record_type} ({l.record_id or '—'})",
                    "Details": l.details or "—",
                }
                for l in logs
            ]
        if l_rows:
            st.dataframe(pd.DataFrame(l_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No audit entries yet.")
