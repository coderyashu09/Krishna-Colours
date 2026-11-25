"""
Streamlit session state management, authentication flows, and logout handlers.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import streamlit as st

from config.settings import settings
from config.database import get_db
from database.models import User
from auth.security import verify_password, is_rate_limited, record_failed_login, reset_failed_login
from auth.permissions import has_permission, is_admin


def init_session_state():
    """Initialize required session state variables."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None
    if "last_activity" not in st.session_state:
        st.session_state.last_activity = datetime.utcnow()
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Dashboard"


def check_session_timeout() -> bool:
    """
    Check if the user session has timed out.
    If timed out, logs the user out.
    Returns True if session is still valid or user not logged in, False if expired.
    """
    if not st.session_state.get("authenticated"):
        return True

    last_active = st.session_state.get("last_activity")
    if last_active:
        timeout_delta = timedelta(minutes=settings.SESSION_TIMEOUT_MINUTES)
        if datetime.utcnow() - last_active > timeout_delta:
            logout_user()
            st.warning("Your session has timed out due to inactivity. Please log in again.")
            return False

    # Update activity timestamp
    st.session_state.last_activity = datetime.utcnow()
    return True


def authenticate_user(username: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Authenticate user against database credentials with rate limiting.
    Returns (success, message, user_dict).
    """
    from sqlalchemy import select

    # Check rate limiting
    locked, remaining_seconds = is_rate_limited(
        username,
        max_attempts=settings.MAX_LOGIN_ATTEMPTS,
        lockout_minutes=settings.LOCKOUT_TIME_MINUTES
    )
    if locked:
        return False, f"Account temporarily locked due to failed attempts. Try again in {remaining_seconds // 60 + 1} minutes.", None

    with get_db() as db:
        user = db.execute(select(User).where(User.username == username.strip())).scalar_one_or_none()

        if not user or not user.is_active:
            is_locked, remaining = record_failed_login(
                username,
                max_attempts=settings.MAX_LOGIN_ATTEMPTS,
                lockout_minutes=settings.LOCKOUT_TIME_MINUTES
            )
            if is_locked:
                return False, f"Account locked due to too many failed attempts. Try again in {settings.LOCKOUT_TIME_MINUTES} minutes.", None
            return False, f"Invalid username or password. {remaining} attempt(s) remaining.", None

        if not verify_password(password, user.password_hash):
            is_locked, remaining = record_failed_login(
                username,
                max_attempts=settings.MAX_LOGIN_ATTEMPTS,
                lockout_minutes=settings.LOCKOUT_TIME_MINUTES
            )
            if is_locked:
                return False, f"Account locked due to too many failed attempts. Try again in {settings.LOCKOUT_TIME_MINUTES} minutes.", None
            return False, f"Invalid username or password. {remaining} attempt(s) remaining.", None

        # Success - reset rate limiter
        reset_failed_login(username)
        user_info = {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
        }
        return True, "Login successful", user_info


def login_user(user_info: Dict[str, Any]):
    """Set authenticated session state."""
    st.session_state.authenticated = True
    st.session_state.user = user_info
    st.session_state.last_activity = datetime.utcnow()


def logout_user():
    """Clear authenticated session state."""
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.last_activity = None
    st.session_state.current_page = "Dashboard"


def get_current_user() -> Optional[Dict[str, Any]]:
    """Return currently logged in user info dict."""
    return st.session_state.get("user")


def user_can(permission: str) -> bool:
    """Convenience helper to check current user's permission."""
    user = get_current_user()
    if not user:
        return False
    return has_permission(user.get("role", "staff"), permission)
