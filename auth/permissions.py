"""
Role-based access control and permission definitions.
Roles: 'admin', 'staff'
"""
from typing import Dict, Set

# Permission matrix defining allowed actions per role
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": {
        # Full access
        "view_dashboard",
        "manage_products",
        "delete_products",
        "manage_stock",
        "override_negative_stock",
        "manage_customers",
        "delete_customers",
        "create_bills",
        "edit_bills",
        "cancel_bills",
        "record_payments",
        "reverse_payments",
        "manage_other_shops",
        "record_returns",
        "mark_return_done",
        "view_reports",
        "export_data",
        "import_data",
        "manage_users",
        "manage_backups",
        "manage_settings",
        "view_audit_logs",
    },
    "staff": {
        # Configurable restricted access (no destructive or system-critical operations)
        "view_dashboard",
        "manage_products",       # Add/Edit allowed, no delete
        "manage_stock",          # Stock In / Out allowed, no override
        "manage_customers",      # Add/Edit allowed, no delete
        "create_bills",
        "record_payments",
        "manage_other_shops",
        "record_returns",
        "view_reports",
    }
}


def has_permission(role: str, permission: str) -> bool:
    """Check if the given role has the requested permission."""
    allowed = ROLE_PERMISSIONS.get(role, set())
    return permission in allowed


def is_admin(role: str) -> bool:
    """Check if user role is administrator."""
    return role == "admin"
