"""
Automated Tests for Authentication, Password Hashing, Session Timeout, and RBAC Permissions.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from auth.security import hash_password, verify_password, is_rate_limited, record_failed_login, reset_failed_login
from auth.permissions import has_permission, is_admin, ROLE_PERMISSIONS
from auth.login import authenticate_user
from config.database import get_db, init_db
from database.models import User


def setup_module():
    init_db()


def test_password_hashing():
    pwd = "1454"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong_password", hashed) is False


def test_initial_admin_authentication():
    # Test valid login with initial password 1454
    success, msg, user_info = authenticate_user("admin", "1454")
    assert success is True
    assert user_info["username"] == "admin"
    assert user_info["role"] == "admin"

    # Test invalid login
    bad_success, bad_msg, bad_info = authenticate_user("admin", "incorrect_pwd")
    assert bad_success is False
    assert bad_info is None


def test_role_permissions():
    # Admin has full privileges
    assert has_permission("admin", "delete_products") is True
    assert has_permission("admin", "manage_backups") is True
    assert is_admin("admin") is True

    # Staff has restricted privileges
    assert has_permission("staff", "create_bills") is True
    assert has_permission("staff", "delete_products") is False
    assert has_permission("staff", "manage_backups") is False
    assert is_admin("staff") is False


def test_rate_limiting():
    test_user = "test_rate_limited_user"
    reset_failed_login(test_user)

    # 4 failed attempts should not lock
    for i in range(4):
        is_locked, remaining = record_failed_login(test_user, max_attempts=5, lockout_minutes=1)
        assert is_locked is False

    # 5th attempt should lock
    is_locked, remaining = record_failed_login(test_user, max_attempts=5, lockout_minutes=1)
    assert is_locked is True

    # Reset should clear lockout
    reset_failed_login(test_user)
    locked_now, _ = is_rate_limited(test_user)
    assert locked_now is False


if __name__ == "__main__":
    setup_module()
    test_password_hashing()
    test_initial_admin_authentication()
    test_role_permissions()
    test_rate_limiting()
    print("test_auth.py: ALL TESTS PASSED!")
