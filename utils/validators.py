"""
Validation utilities for inputs: phone numbers, GSTIN, numeric constraints, etc.
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Tuple, Optional, Any


def validate_mobile(mobile: str) -> Tuple[bool, str]:
    """Validate 10-digit Indian mobile number."""
    if not mobile:
        return False, "Mobile number is required."
    clean = re.sub(r"[\s\-\+]", "", str(mobile))
    if clean.startswith("91") and len(clean) == 12:
        clean = clean[2:]
    if len(clean) != 10 or not clean.isdigit():
        return False, f"Invalid mobile number '{mobile}'. Must be a 10-digit numeric phone number."
    return True, clean


def validate_gstin(gstin: Optional[str]) -> Tuple[bool, str]:
    """Validate Indian GSTIN format (15 characters: 2 state, 10 PAN, 1 entity, 1 'Z', 1 checksum)."""
    if not gstin or not gstin.strip():
        return True, ""
    clean = gstin.strip().upper()
    gstin_pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
    if not re.match(gstin_pattern, clean):
        return False, f"Invalid GSTIN format '{gstin}'. Standard format: 24AAAAA0000A1Z5."
    return True, clean


def parse_decimal(value: Any, default: Decimal = Decimal("0.00"), field_name: str = "Amount") -> Decimal:
    """Safely parse input to Decimal without floating point imprecision."""
    if value is None or str(value).strip() == "":
        return default
    try:
        clean_str = str(value).replace(",", "").strip()
        return Decimal(clean_str)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid numeric value for {field_name}: '{value}'")
