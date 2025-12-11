"""
JSON utilities for cross-platform file operations
Stateless module functions - no classes needed
"""

import json
from typing import Any, Dict, Union, Optional, TypeVar, Generic

T = TypeVar("T")


def write_file(path: str, data: Any) -> str:
    """Write JSON data to file (pretty formatted)"""
    content = json.dumps(data, indent=2)
    from aicoder.utils.file_utils import write_file as file_write

    return file_write(path, content)


def read_file(path: str, default_type: type = dict) -> Any:
    """Read and parse JSON from file"""
    from aicoder.utils.file_utils import read_file as file_read

    content = file_read(path)
    return json.loads(content)


def read_file_safe(path: str, default: Any = None) -> Any:
    """Read and parse JSON from file (safe version)"""
    try:
        from aicoder.utils.file_utils import read_file as file_read

        content = file_read(path)
        return json.loads(content)
    except Exception:
        return default


def is_valid(json_string: str) -> bool:
    """Validate JSON string"""
    try:
        json.loads(json_string)
        return True
    except Exception:
        return False


def parse_safe(json_string: str, default: Any = None) -> Any:
    """Parse JSON string safely"""
    try:
        return json.loads(json_string)
    except Exception:
        return default
