"""
Path utilities for security and validation
Ported exactly from TypeScript version
"""


def is_safe_path(path: str) -> bool:
    """Check if a path is safe (no parent directory traversal)"""
    # Check for obvious parent directory traversal
    return "../" not in path


def validate_path(path: str, context: str = "operation") -> bool:
    """Validate path and log security warning if unsafe"""
    if not is_safe_path(path):
        print(
            f'\x1b[33m[x] Sandbox: {context} trying to access "{path}" (contains parent traversal)\x1b[0m'
        )
        return False
    return True


def validate_tool_path(path: str, tool_name: str) -> bool:
    """Validate path for tools with specific logging format"""
    if not is_safe_path(path):
        print(
            f'\x1b[33m[x] Sandbox: {tool_name} trying to access "{path}" (contains parent traversal)\x1b[0m'
        )
        return False
    return True
