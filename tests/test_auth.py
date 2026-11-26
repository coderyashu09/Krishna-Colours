"""
Automated Tests for Authentication, Password Hashing, Rate Limiting, and RBAC Permissions.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.security import hash_password, verify_password, is_rate_limited, record_failed_login, reset_failed_login
from auth.permissions import has_permission, is_admin
from auth.login import authenticate_user
from config.database import init_db


def setup_module():
    init_db()


def test_password_hashing():
    pwd = "1454"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong_password", hashed) is False


def test_initial_admin_authentication():
    reset_failed_login("admin")
    success, msg, user_info = authenticate_user("admin", "1454")
    assert success is True
    assert user_info["username"] == "admin"
    assert user_info["role"] == "admin"

    bad_success, _, bad_info = authenticate_user("admin", "incorrect_pwd")
    assert bad_success is False
    assert bad_info is None
    reset_failed_login("admin")


def test_role_permissions():
    assert has_permission("admin", "manage_items") is True
    assert has_permission("admin", "manage_backups") is True
    assert has_permission("admin", "manage_customers") is True
    assert is_admin("admin") is True

    assert has_permission("staff", "manage_customers") is True
    assert has_permission("staff", "manage_bills") is True
    assert has_permission("staff", "manage_items") is False
    assert has_permission("staff", "manage_backups") is False
    assert is_admin("staff") is False


def test_rate_limiting():
    test_user = "test_rate_limited_user"
    reset_failed_login(test_user)

    for _ in range(4):
        is_locked, _ = record_failed_login(test_user, max_attempts=5, lockout_minutes=1)
        assert is_locked is False

    is_locked, _ = record_failed_login(test_user, max_attempts=5, lockout_minutes=1)
    assert is_locked is True

    reset_failed_login(test_user)
    locked_now, _ = is_rate_limited(test_user)
    assert locked_now is False
