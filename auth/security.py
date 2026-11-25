"""
Security utilities: Password hashing (Argon2 with bcrypt fallback)
and login attempt rate limiting.
"""
import time
from typing import Dict, Tuple

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHashError
    _hasher = PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=2,
        hash_len=32,
        salt_len=16
    )
    USE_ARGON2 = True
except ImportError:
    USE_ARGON2 = False

import bcrypt

# Rate limiter store: username -> (failure_count, lockout_until_timestamp)
_LOGIN_ATTEMPTS: Dict[str, Tuple[int, float]] = {}


def hash_password(password: str) -> str:
    """Hash password using Argon2id or bcrypt."""
    if not password:
        raise ValueError("Password cannot be empty.")
    if USE_ARGON2:
        return _hasher.hash(password)
    else:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify password against stored hash."""
    if not password or not hashed_password:
        return False
    if USE_ARGON2 and (hashed_password.startswith("$argon2") or hashed_password.startswith("$argon2id")):
        try:
            return _hasher.verify(hashed_password, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
    else:
        # Fallback to bcrypt verification
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False


def is_rate_limited(username: str, max_attempts: int = 5, lockout_minutes: int = 15) -> Tuple[bool, int]:
    """
    Check if a username is currently locked out due to too many failed attempts.
    Returns (is_locked, remaining_seconds).
    """
    now = time.time()
    record = _LOGIN_ATTEMPTS.get(username)
    if not record:
        return False, 0
    failures, lockout_until = record
    if lockout_until > now:
        return True, int(lockout_until - now)
    return False, 0


def record_failed_login(username: str, max_attempts: int = 5, lockout_minutes: int = 15) -> Tuple[bool, int]:
    """
    Record a failed login attempt. If threshold reached, activates lockout.
    Returns (is_now_locked, remaining_attempts_or_lockout_seconds).
    """
    now = time.time()
    record = _LOGIN_ATTEMPTS.get(username)
    failures = 0
    if record:
        failures, lockout_until = record
        if lockout_until > now:
            return True, int(lockout_until - now)
        elif lockout_until > 0:
            # Lockout expired, reset counter
            failures = 0

    failures += 1
    if failures >= max_attempts:
        lockout_until = now + (lockout_minutes * 60)
        _LOGIN_ATTEMPTS[username] = (failures, lockout_until)
        return True, int(lockout_minutes * 60)
    else:
        _LOGIN_ATTEMPTS[username] = (failures, 0)
        return False, max_attempts - failures


def reset_failed_login(username: str):
    """Clear failed login attempts upon successful login."""
    if username in _LOGIN_ATTEMPTS:
        del _LOGIN_ATTEMPTS[username]
