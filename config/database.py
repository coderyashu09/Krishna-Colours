"""
Database engine, session management, safe migration, and initialization
for Krishna Colour – Asian Paints Customer Management System.
Supports Supabase PostgreSQL and SQLite fallback.
"""
import logging
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import StaticPool

from config.settings import settings
from database.models import Base, User
from database.seed_asian_paints import seed_initial_dropdown_items

logger = logging.getLogger(__name__)

db_url = settings.DATABASE_URL
engine_kwargs = {"echo": False, "future": True}

if db_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in db_url:
        engine_kwargs["poolclass"] = StaticPool
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(db_url, **engine_kwargs)
SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
ScopedSession = scoped_session(SessionFactory)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for database sessions with automatic commit/rollback."""
    session = ScopedSession()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session rollback due to error: {e}")
        raise
    finally:
        session.close()


def _cleanup_legacy_erp_sqlite_tables():
    """
    Safely back up the SQLite database if legacy unrelated ERP tables exist,
    then drop only the obsolete ERP tables while preserving `users` and backups.
    """
    if not db_url.startswith("sqlite") or ":memory:" in db_url:
        return

    db_path_str = db_url.replace("sqlite:///", "")
    db_file = Path(db_path_str)
    if not db_file.is_absolute():
        db_file = settings.BACKUP_DIR.parent / db_file
    if not db_file.exists():
        return

    legacy_tables = [
        "shop_return_items", "shop_returns", "shop_issue_items", "shop_issues",
        "other_shops", "stock_transactions", "product_variants", "products",
        "product_categories", "categories", "suppliers", "business_settings",
        "payments", "bills",
    ]

    conn = sqlite3.connect(str(db_file))
    try:
        existing = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        has_legacy = any(t in existing for t in legacy_tables)
        # Also clean old test customers if customer_bills doesn't exist yet (migrating from ERP phase)
        if has_legacy:
            settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup_copy = settings.BACKUP_DIR / f"pre_cms_migration_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(db_file, backup_copy)

            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys = OFF;")
            for lt in legacy_tables:
                if lt in existing:
                    cur.execute(f'DROP TABLE IF EXISTS "{lt}";')
            # If old ERP bill_items or test customers exist before CMS schema existed, reset them cleanly
            if "customer_bills" not in existing:
                if "bill_items" in existing:
                    cur.execute('DROP TABLE IF EXISTS "bill_items";')
                if "customers" in existing:
                    # Only remove automated test rows from prior phase; preserve real rows if any
                    rows = cur.execute("SELECT id, customer_code FROM customers").fetchall()
                    all_test = all(
                        str(code).startswith(("KC-TEST-", "KC-PAY-")) for _, code in rows
                    )
                    if all_test:
                        cur.execute('DROP TABLE IF EXISTS "customers";')
            cur.execute("PRAGMA foreign_keys = ON;")
            conn.commit()
        if "customer_bills" in existing:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(customer_bills)").fetchall()}
            if "has_pending" not in cols:
                conn.execute("ALTER TABLE customer_bills ADD COLUMN has_pending BOOLEAN NOT NULL DEFAULT 0;")
            if "original_amount" in cols:
                try:
                    conn.execute("ALTER TABLE customer_bills DROP COLUMN original_amount;")
                except Exception:
                    pass
            conn.commit()
    finally:
        conn.close()


def init_db(force_recreate: bool = False):
    """
    Initialize Customer Management System tables, preserve user auth,
    and seed initial dropdown items if empty.
    """
    from auth.security import hash_password

    if not force_recreate:
        _cleanup_legacy_erp_sqlite_tables()
    else:
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)

    with get_db() as db:
        admin_user = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
        if not admin_user:
            hashed = hash_password(settings.INITIAL_ADMIN_PASSWORD)
            db.add(
                User(
                    username="admin",
                    password_hash=hashed,
                    full_name="Business Administrator",
                    role="admin",
                    is_active=True,
                )
            )
            logger.info("Created default administrator account.")

        seed_initial_dropdown_items(db, force=False)
