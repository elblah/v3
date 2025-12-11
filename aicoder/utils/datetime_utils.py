"""
Date and time utilities
Ported exactly from TypeScript version
"""

from datetime import datetime
import time


def create_file_timestamp() -> str:
    """Create a filesystem-safe timestamp from current date
    Format: YYYY-MM-DDTHH-MM-SS (first 19 chars of ISO string with colons replaced)
    """
    return datetime.now().isoformat().replace(":", "-")[0:19]


def create_timestamp_filename(prefix: str, extension: str = "") -> str:
    """Create a filename with timestamp"""
    timestamp = create_file_timestamp()
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"{prefix}-{timestamp}{ext}"


def get_current_iso_datetime() -> str:
    """Get current ISO datetime string"""
    return datetime.now().isoformat()
