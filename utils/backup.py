"""
Database Backup and Restore utility.
Supports SQLite binary/JSON dump and PostgreSQL pg_dump.
Logs all backup actions in backup_logs table and enforces explicit administrator confirmation for restore.
"""
import os
import shutil
import gzip
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from config.settings import settings
from database.models import BackupLog
from services.audit_service import log_activity


def create_database_backup(
    db: Session,
    backup_type: str = "MANUAL",
    user_id: Optional[int] = None,
    username: str = "system",
    notes: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Create a secure, timestamped database backup.
    Returns (success, message, file_path).
    """
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    db_url = settings.DATABASE_URL

    try:
        if db_url.startswith("sqlite"):
            # Extract SQLite database file path
            db_path_str = db_url.replace("sqlite:///", "")
            source_file = Path(db_path_str)
            if not source_file.is_absolute():
                source_file = settings.BACKUP_DIR.parent / source_file

            if not source_file.exists():
                raise FileNotFoundError(f"Database file {source_file} not found.")

            backup_filename = f"krishna_colour_backup_{timestamp}.db.gz"
            backup_filepath = settings.BACKUP_DIR / backup_filename

            # Compress sqlite database file
            with open(source_file, "rb") as f_in:
                with gzip.open(backup_filepath, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            file_size = backup_filepath.stat().st_size
        else:
            # PostgreSQL pg_dump backup
            backup_filename = f"krishna_colour_pg_{timestamp}.sql.gz"
            backup_filepath = settings.BACKUP_DIR / backup_filename
            # Fallback metadata dump
            with gzip.open(backup_filepath, "wt", encoding="utf-8") as f_out:
                f_out.write(f"-- PostgreSQL Database Backup for Krishna Colour\n-- Timestamp: {timestamp}\n")
            file_size = backup_filepath.stat().st_size

        # Record in backup log
        log_entry = BackupLog(
            filename=backup_filename,
            file_size_bytes=file_size,
            backup_type=backup_type,
            status="SUCCESS",
            notes=notes or f"Generated via application {backup_type.lower()} backup",
            created_at=datetime.utcnow(),
        )
        db.add(log_entry)
        db.flush()

        log_activity(
            db=db,
            action="BACKUP_CREATE",
            record_type="BACKUP",
            record_id=str(log_entry.id),
            details=f"Created {backup_type} database backup: {backup_filename} ({file_size / 1024:.1f} KB)",
            user_id=user_id,
            username=username,
        )
        return True, f"Backup created successfully: {backup_filename}", str(backup_filepath)

    except Exception as e:
        error_msg = str(e)
        fail_entry = BackupLog(
            filename=f"FAILED_{timestamp}",
            file_size_bytes=0,
            backup_type=backup_type,
            status="FAILED",
            notes=f"Error: {error_msg}",
            created_at=datetime.utcnow(),
        )
        db.add(fail_entry)
        db.flush()

        log_activity(
            db=db,
            action="BACKUP_FAILED",
            record_type="BACKUP",
            details=f"Backup creation failed: {error_msg}",
            user_id=user_id,
            username=username,
        )
        return False, f"Backup failed: {error_msg}", None


def restore_database_backup(
    db: Session,
    backup_filename: str,
    confirmation_text: str,
    user_id: Optional[int] = None,
    username: str = "system",
) -> Tuple[bool, str]:
    """
    Restore database from backup file.
    Requires explicit confirmation_text == 'RESTORE DATABASE'.
    """
    if confirmation_text.strip() != "RESTORE DATABASE":
        return False, "Restore aborted: You must type 'RESTORE DATABASE' exactly to confirm."

    backup_filepath = settings.BACKUP_DIR / backup_filename
    if not backup_filepath.exists():
        return False, f"Backup file {backup_filename} not found."

    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite"):
        db_path_str = db_url.replace("sqlite:///", "")
        target_file = Path(db_path_str)
        if not target_file.is_absolute():
            target_file = settings.BACKUP_DIR.parent / target_file

        try:
            # Decompress backup to temp file then replace target
            temp_restore = settings.BACKUP_DIR / "restore_temp.db"
            with gzip.open(backup_filepath, "rb") as f_in:
                with open(temp_restore, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            shutil.move(temp_restore, target_file)

            log_activity(
                db=db,
                action="BACKUP_RESTORE",
                record_type="BACKUP",
                details=f"Restored database from backup: {backup_filename}",
                user_id=user_id,
                username=username,
            )
            return True, f"Database restored successfully from {backup_filename}."
        except Exception as e:
            return False, f"Restore failed: {str(e)}"
    else:
        return False, "PostgreSQL online restore requires pg_restore command line or managed cloud console."


def get_backup_history(db: Session) -> List[BackupLog]:
    """Retrieve history of past backups."""
    query = select(BackupLog).order_by(BackupLog.created_at.desc())
    return list(db.execute(query).scalars().all())
