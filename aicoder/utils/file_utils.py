"""
Cross-platform file operations with sandbox enforcement
Stateless module functions - no classes needed
"""

import os
from pathlib import Path
from typing import Set

# Module-level state
_current_dir = os.getcwd()
_read_files: Set[str] = set()


def get_current_dir() -> str:
    """Get current working directory"""
    return _current_dir


def get_relative_path(path: str) -> str:
    """Get relative path from current working directory"""
    try:
        # Use Path to get relative path
        current = Path(_current_dir)
        target = Path(path).resolve()
        
        # If target is within current directory, return relative path
        try:
            return str(target.relative_to(current))
        except ValueError:
            # If not within current directory, return absolute path
            return str(target)
    except Exception:
        # Fallback to original path
        return path


def check_sandbox(path: str, context: str = "file operation") -> bool:
    """Check if a path is allowed by sandbox rules"""
    # Import here to avoid circular imports
    try:
        from aicoder.core.config import Config
    except ImportError:
        # Config not available - allow everything
        return True

    if Config.sandbox_disabled():
        return True

    if not path:
        return True

    # Resolve relative paths using pathlib
    resolved_path = str(Path(path).resolve())

    # Ensure current directory has trailing slash for proper prefix matching
    current_dir_with_slash = (
        _current_dir if _current_dir.endswith("/") else _current_dir + "/"
    )

    # Check if resolved path is within current directory
    # Must either be exactly current dir or start with current dir + '/'
    if not (
        resolved_path == _current_dir
        or resolved_path.startswith(current_dir_with_slash)
    ):
        try:
            from aicoder.utils.log import warn
            warn(f'Sandbox: {context} trying to access "{resolved_path}" outside current directory "{_current_dir}"')
        except ImportError:
            # Fallback if log utils not available
            import sys
            print(
                f'[x] Sandbox: {context} trying to access "{path}" (contains parent traversal)',
                file=sys.stderr
            )
        return False

    return True


def file_exists(path: str) -> bool:
    """Check if file exists (no sandbox)"""
    return os.path.exists(path)


def read_file(path: str) -> str:
    """Read a file (no sandbox) - default behavior for internal use"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        _read_files.add(path)
        return content
    except Exception as error:
        raise Exception(f"Error reading file '{path}': {error}")


def read_file_with_sandbox(path: str) -> str:
    """Read a file with sandbox check - for AI requests only"""
    # Check sandbox first
    if not check_sandbox(path, "read_file"):
        raise Exception(
            f'read_file: path "{path}" outside current directory not allowed'
        )

    return read_file(path)


def write_file(path: str, content: str) -> str:
    """Write to a file (no sandbox) - default behavior for internal use"""
    try:
        # Create directory if it doesn't exist
        dir_path = os.path.dirname(path)
        if dir_path:  # Only create if there's actually a directory path
            os.makedirs(dir_path, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        bytes_count = len(content.encode("utf-8"))
        lines_count = len(content.split("\n"))
        return f"Successfully wrote {bytes_count} bytes ({lines_count} lines) to {path}"
    except Exception as error:
        raise Exception(f"Error writing file '{path}': {error}")


def write_file_with_sandbox(path: str, content: str) -> str:
    """Write to a file with sandbox check - for AI requests only"""
    # Check sandbox first
    if not check_sandbox(path, "write_file"):
        raise Exception(
            f'write_file: path "{path}" outside current directory not allowed'
        )

    return write_file(path, content)


def list_directory(path: str) -> list:
    """List directory contents (with sandbox check)"""
    # Resolve path first
    resolved_path = str(Path(path).resolve()) if path != "." else _current_dir

    # Check sandbox
    if not check_sandbox(resolved_path, "list_directory"):
        raise Exception(
            f'list_directory: path "{path}" (resolves to "{resolved_path}") outside current directory not allowed'
        )

    try:
        entries = os.listdir(resolved_path)

        # Filter only files/dirs (no special entries)
        excluded = ["node_modules", ".git", ".vscode", ".idea", "dist", "build"]
        valid_entries = []

        for entry in entries:
            if not entry.startswith(".") and entry not in excluded:
                valid_entries.append(entry)

        return valid_entries
    except Exception as error:
        raise Exception(f"Error listing directory '{resolved_path}': {error}")


def get_read_files() -> Set[str]:
    """Get set of files that have been read"""
    return _read_files.copy()
