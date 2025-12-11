"""
Cross-platform temporary file utilities
Ported exactly from TypeScript version
"""

import os
import time
import random
from typing import Optional


def get_temp_dir() -> str:
    """Get system temp directory"""
    # Try to use local tmp directory first to avoid sandbox issues
    local_tmp = "./tmp"
    try:
        local_tmp_path = os.path.abspath(os.path.join(os.getcwd(), local_tmp))
        os.makedirs(local_tmp_path, exist_ok=True)
        return local_tmp_path
    except Exception:
        # Fall back to other options
        pass

    # Try system temp directory
    tmp_dir = os.environ.get("TMPDIR")
    if tmp_dir:
        return tmp_dir

    # Fallback to /tmp for Unix-like systems
    return "/tmp"


def create_temp_file(prefix: str, suffix: str = "") -> str:
    """Create a temporary file path"""
    temp_dir = get_temp_dir()
    timestamp = int(time.time())
    random_num = random.randint(0, 9999)
    file_name = f"{prefix}-{timestamp}-{random_num}{suffix}"

    return os.path.join(temp_dir, file_name)


def delete_file(path: str) -> None:
    """Delete a file"""
    try:
        os.remove(path)
    except Exception:
        # Ignore deletion errors (file might not exist)
        pass


def delete_file_sync(path: str) -> None:
    """Delete file synchronously"""
    delete_file(path)


def write_temp_file(path: str, content: str) -> None:
    """Write to temp file and ensure cleanup"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
