"""
Database engine, session management, and initialization for Krishna Colour.
Supports PostgreSQL (production) with automatic SQLite fallback for zero-config local operation.
"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import StaticPool

from config.settings import settings
from database.models import Base, User, Category, BusinessSetting

logger = logging.getLogger(__name__)

# Configure engine arguments
db_url = settings.DATABASE_URL
engine_kwargs = {"echo": False, "future": True}

if db_url.startswith("sqlite"):
    # SQLite specific configuration
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in db_url:
        engine_kwargs["poolclass"] = StaticPool
else:
    # PostgreSQL pool settings
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


def init_db(force_recreate: bool = False):
    """
    Initialize all database tables and seed mandatory initial state
    (Initial Admin user with secure hash, standard paint categories, initial business settings).
    Zero fake products or fake customer records are created.
    """
    from auth.security import hash_password

    if force_recreate:
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)

    with get_db() as db:
        # 1. Initialize Admin User if none exists
        admin_user = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
        if not admin_user:
            initial_password = settings.INITIAL_ADMIN_PASSWORD
            hashed = hash_password(initial_password)
            admin = User(
                username="admin",
                password_hash=hashed,
                full_name="Business Administrator",
                role="admin",
                is_active=True
            )
            db.add(admin)
            logger.info("Created default administrator account.")

        # 2. Seed Standard Paint Categories (Asian Paints Industry Standard)
        standard_categories = [
            ("Interior Wall Paints", "Emulsions, primers, and distempers for interior walls"),
            ("Exterior Wall Paints", "Weatherproof exterior emulsions and finishes"),
            ("Wood & Metal Finishes", "Enamels, PU coats, wood stains, and varnishes"),
            ("Waterproofing & Primers", "Damp-proof coatings, sealers, and undercoats"),
            ("Wall Putty & Plasters", "Base preparation, acrylic and white cement putty"),
            ("Painting Tools & Brushes", "Rollers, brushes, sandpaper, masking tape, and trays"),
            ("Thinner & Solvents", "Mineral turpentine, NC thinners, and general thinners"),
            ("Colourants & Strainers", "Universal stainers and machine tinting colorants"),
        ]
        for cat_name, cat_desc in standard_categories:
            existing_cat = db.execute(select(Category).where(Category.name == cat_name)).scalar_one_or_none()
            if not existing_cat:
                db.add(Category(name=cat_name, description=cat_desc))

        # 3. Seed Initial Business Settings
        default_settings = {
            "shop_name": settings.APP_NAME,
            "shop_tagline": settings.APP_TAGLINE,
            "shop_address": settings.APP_ADDRESS,
            "shop_phone": settings.APP_PHONE,
            "shop_gstin": settings.APP_GSTIN,
            "shop_state": settings.APP_STATE,
            "bill_prefix": "KC-",
            "invoice_terms": "1. Goods once sold will not be accepted without invoice.\n2. Asian Paints manufacturer warranty applies.\n3. Subject to local jurisdiction.",
            "low_stock_threshold_default": "5",
            "currency_symbol": "₹",
        }
        for key, val in default_settings.items():
            setting_obj = db.execute(select(BusinessSetting).where(BusinessSetting.setting_key == key)).scalar_one_or_none()
            if not setting_obj:
                db.add(BusinessSetting(setting_key=key, setting_value=val, description=f"Default {key}"))

        db.commit()
