"""
Role-based access control and permission definitions for Krishna Colour Customer Management System.
Roles: 'admin', 'staff'
"""
from typing import Dict, Set

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": {
        "view_dashboard",
        "manage_customers",
        "delete_customers",
        "manage_bills",
        "record_payments",
        "manage_items",
        "manage_users",
        "manage_backups",
        "manage_settings",
        "view_audit_logs",
    },
    "staff": {
        "view_dashboard",
        "manage_customers",
        "manage_bills",
        "record_payments",
    },
}


def has_permission(role: str, permission: str) -> bool:
    """Check if the given role has the requested permission."""
    allowed = ROLE_PERMISSIONS.get(role, set())
    return permission in allowed


def is_admin(role: str) -> bool:
    """Check if user role is administrator."""
    return role == "admin"
