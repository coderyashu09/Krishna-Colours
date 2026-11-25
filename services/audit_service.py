"""
Audit logging service for tracking critical operations across Krishna Colour.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from database.models import AuditLog


def log_activity(
    db: Session,
    action: str,
    record_type: str,
    record_id: Optional[str] = None,
    details: Optional[str] = None,
    user_id: Optional[int] = None,
    username: str = "system",
    ip_address: Optional[str] = None,
):
    """Record an audit trail entry."""
    entry = AuditLog(
        user_id=user_id,
        username=username or "system",
        action=action,
        record_type=record_type,
        record_id=str(record_id) if record_id else None,
        details=details,
        ip_address=ip_address,
        created_at=datetime.utcnow()
    )
    db.add(entry)
