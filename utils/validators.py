"""
EdgeCase Input Validators
Basic validation functions for data integrity.

Note: Jinja2 autoescaping handles XSS protection in templates.
These validators are for data quality, not security.
"""

import re
from typing import Optional, Tuple


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """Validate email format.
    
    Returns:
        (True, None) if valid
        (False, error_message) if invalid
    """
    if not email:
        return True, None  # Empty is OK (field is optional)
    
    # Basic email pattern - intentionally permissive
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if re.match(pattern, email):
        return True, None
    return False, "Invalid email format"


def validate_phone(phone: str) -> Tuple[bool, Optional[str]]:
    """Validate phone number format.
    
    Accepts various formats:
    - (613) 555-1234
    - 613-555-1234
    - 6135551234
    - +1 613 555 1234
    
    Returns:
        (True, None) if valid
        (False, error_message) if invalid
    """
    if not phone:
        return True, None  # Empty is OK (field is optional)
    
    # Strip common separators and check if remaining chars are digits or + 
    cleaned = re.sub(r'[\s\-\(\)\.]', '', phone)
    
    # Allow + at start for country code
    if cleaned.startswith('+'):
        cleaned = cleaned[1:]
    
    if cleaned.isdigit() and 7 <= len(cleaned) <= 15:
        return True, None
    return False, "Invalid phone number format"


def validate_fee(fee: float, allow_negative: bool = False) -> Tuple[bool, Optional[str]]:
    """Validate fee amount.
    
    Args:
        fee: The fee amount to validate
        allow_negative: Whether to allow negative values (for credits)
    
    Returns:
        (True, None) if valid
        (False, error_message) if invalid
    """
    if fee is None:
        return True, None
    
    try:
        fee = float(fee)
    except (ValueError, TypeError):
        return False, "Fee must be a number"
    
    if not allow_negative and fee < 0:
        return False, "Fee cannot be negative"
    
    # Sanity check - no fee should be over $10,000 per session
    if abs(fee) > 10000:
        return False, "Fee exceeds maximum allowed ($10,000)"
    
    return True, None


def validate_tax_rate(rate: float) -> Tuple[bool, Optional[str]]:
    """Validate tax rate percentage.
    
    Args:
        rate: Tax rate as percentage (e.g., 13 for 13%)
    
    Returns:
        (True, None) if valid
        (False, error_message) if invalid
    """
    if rate is None:
        return True, None
    
    try:
        rate = float(rate)
    except (ValueError, TypeError):
        return False, "Tax rate must be a number"
    
    if rate < 0:
        return False, "Tax rate cannot be negative"
    
    if rate > 50:
        return False, "Tax rate exceeds 50%"
    
    return True, None


def validate_percentage(value: float, field_name: str = "Value") -> Tuple[bool, Optional[str]]:
    """Validate a percentage value (0-100).
    
    Returns:
        (True, None) if valid
        (False, error_message) if invalid
    """
    if value is None:
        return True, None
    
    try:
        value = float(value)
    except (ValueError, TypeError):
        return False, f"{field_name} must be a number"
    
    if value < 0 or value > 100:
        return False, f"{field_name} must be between 0 and 100"
    
    return True, None


def validate_file_number(file_number: str) -> Tuple[bool, Optional[str]]:
    """Validate file number format.
    
    File numbers should be non-empty and not contain problematic characters.
    
    Returns:
        (True, None) if valid
        (False, error_message) if invalid
    """
    if not file_number:
        return False, "File number is required"
    
    if len(file_number) > 50:
        return False, "File number too long (max 50 characters)"
    
    # Disallow characters that could cause filesystem or display issues
    forbidden = ['/', '\\', '<', '>', ':', '"', '|', '?', '*']
    for char in forbidden:
        if char in file_number:
            return False, f"File number cannot contain '{char}'"
    
    return True, None


def validate_required_string(value: str, field_name: str, max_length: int = 255) -> Tuple[bool, Optional[str]]:
    """Validate a required string field.
    
    Returns:
        (True, None) if valid
        (False, error_message) if invalid
    """
    if not value or not value.strip():
        return False, f"{field_name} is required"
    
    if len(value) > max_length:
        return False, f"{field_name} too long (max {max_length} characters)"
    
    return True, None


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe storage.
    
    This is a backup to werkzeug.utils.secure_filename.
    """
    # Remove directory components
    filename = filename.replace('/', '_').replace('\\', '_')
    
    # Remove other problematic characters
    filename = re.sub(r'[<>:"|?*]', '_', filename)
    
    # Collapse multiple underscores
    filename = re.sub(r'_+', '_', filename)
    
    # Ensure not empty
    if not filename or filename == '_':
        filename = 'unnamed_file'
    
    return filename
