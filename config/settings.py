"""
Configuration management for Krishna Colour - Asian Paints.
Loads settings from Streamlit secrets, environment variables, and .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def get_secret(key: str, default: str = "") -> str:
    """Retrieve secret from Streamlit secrets or OS environment."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


class Settings:
    # Application Info
    APP_NAME: str = get_secret("SHOP_NAME", "Krishna Colour – Asian Paints")
    APP_TAGLINE: str = get_secret("SHOP_TAGLINE", "Authorized Dealer for Asian Paints")
    APP_ADDRESS: str = get_secret("SHOP_ADDRESS", "Main Road, Market Area")
    APP_PHONE: str = get_secret("SHOP_PHONE", "+91 98765 43210")
    APP_GSTIN: str = get_secret("SHOP_GSTIN", "24AAAAA0000A1Z5")
    APP_STATE: str = get_secret("SHOP_STATE", "Gujarat (24)")

    # Database
    DATABASE_URL: str = get_secret("DATABASE_URL", f"sqlite:///{BASE_DIR / 'krishna_colour.db'}")

    # Security & Auth
    INITIAL_ADMIN_PASSWORD: str = get_secret("INITIAL_ADMIN_PASSWORD", "1454")
    SECRET_KEY: str = get_secret("SECRET_KEY", "krishna-colour-super-secret-key-2026")
    SESSION_TIMEOUT_MINUTES: int = int(get_secret("SESSION_TIMEOUT_MINUTES", "60"))
    MAX_LOGIN_ATTEMPTS: int = int(get_secret("MAX_LOGIN_ATTEMPTS", "5"))
    LOCKOUT_TIME_MINUTES: int = int(get_secret("LOCKOUT_TIME_MINUTES", "15"))

    # UI Theme Palette
    COLOR_BG: str = "#F8FAFC"
    COLOR_SURFACE: str = "#FFFFFF"
    COLOR_TEXT_PRIMARY: str = "#172033"
    COLOR_TEXT_SECONDARY: str = "#64748B"
    COLOR_ACCENT: str = "#2563EB"
    COLOR_SUCCESS: str = "#16A34A"
    COLOR_WARNING: str = "#D97706"
    COLOR_DANGER: str = "#DC2626"
    COLOR_BORDER: str = "#E5E7EB"

    # Paths
    BACKUP_DIR: Path = BASE_DIR / "backups"
    ASSETS_DIR: Path = BASE_DIR / "assets"


settings = Settings()
settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
