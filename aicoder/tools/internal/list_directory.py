"""
List directory tool

"""

import fnmatch
import os
from typing import Dict, Any
from aicoder.core.config import Config


def validateArguments(args: Dict[str, Any]) -> None:
    """Validate list directory arguments"""
    path = args.get("path")
    if not path or path.strip() == "":
        args["path"] = "."


def formatArguments(args: Dict[str, Any]) -> str:
    """Format arguments for approval display"""
    path = args.get("path", ".")
    pattern = args.get("pattern")
    if pattern:
        return f"Listing '{path}' matching: {pattern}"
    if path and path != ".":
        return f"Listing directory: {path}"
    return ""


def execute(args: Dict[str, Any]) -> Dict[str, Any]:
    """List directory contents using os.walk with ignore dir filtering"""
    path = args.get("path", ".")
    pattern = args.get("pattern")
    MAX_FILES = 100

    try:
        # Resolve path
        import os

        resolved_path = os.path.abspath(path)

        # Check sandbox restrictions
        if not _check_sandbox(resolved_path, print_message=False):
            sandbox_msg = f'Path: {path}\n[x] Sandbox: trying to access "{resolved_path}" outside current directory "{os.getcwd()}"'
            return {
                "tool": "list_directory",
                "friendly": sandbox_msg,
                "detailed": sandbox_msg
            }

        # Check if path exists and is a directory
        if not os.path.exists(resolved_path) or not os.path.isdir(resolved_path):
            return {
                "tool": "list_directory",
                "friendly": f"Directory not found: '{resolved_path}'",
                "detailed": f"Directory not found at '{resolved_path}'. Path does not exist or is not a directory."
            }

        # Get directories and patterns to ignore
        ignore_dirs = set(Config.ignore_dirs())
        ignore_patterns = Config.ignore_patterns()

        # Use os.walk to list files with ignore dir filtering
        files = []
        for root, dirs, filenames in os.walk(resolved_path):
            # Filter dirs in-place to skip them in recursion
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            for filename in filenames:
                # Skip files matching ignore patterns
                if any(filename.endswith(p) for p in ignore_patterns):
                    continue

                # Skip files not matching pattern if specified
                if pattern and not fnmatch.fnmatch(filename, pattern):
                    continue

                full_path = os.path.join(root, filename)
                files.append(full_path)

                # Stop early if we have enough files
                if len(files) >= MAX_FILES + 1:
                    break

            if len(files) >= MAX_FILES + 1:
                break

        actual_count = len(files)
        limited_files = files[:MAX_FILES]

        # Create output
        if limited_files == []:
            return {
                "tool": "list_directory",
                "friendly": f"Directory is empty: '{resolved_path}'",
                "detailed": f"Directory '{resolved_path}' exists but contains no files or subdirectories."
            }
        elif actual_count > MAX_FILES:
            return {
                "tool": "list_directory",
                "friendly": f"Found {MAX_FILES}+ files in '{resolved_path}'",
                "detailed": f"Showing first {MAX_FILES} files:\n\n{chr(10).join(limited_files)}"
            }
        else:
            return {
                "tool": "list_directory",
                "friendly": f"✓ Found {actual_count} files in '{resolved_path}'",
                "detailed": f"Directory '{resolved_path}' contents:\n\n{chr(10).join(limited_files)}"
            }

    except Exception as e:
        return {
            "tool": "list_directory",
            "friendly": f"❌ Error listing directory: {str(e)}",
            "detailed": f"Error listing directory '{path}': {str(e)}"
        }


def _list_single(path: str, show_hidden: bool) -> list:
    """List single directory"""
    try:
        items = os.listdir(path)
    except OSError as e:
        raise Exception(f"Cannot list directory: {e}")

    if not show_hidden:
        items = [item for item in items if not item.startswith(".")]

    return items


def _list_recursive(path: str, max_depth: int, show_hidden: bool) -> list:
    """List directory recursively"""
    result = []

    def _walk(current_path: str, depth: int):
        if depth > max_depth:
            return

        try:
            items = os.listdir(current_path)
        except OSError:
            return

        for item in items:
            if not show_hidden and item.startswith("."):
                continue

            full_path = os.path.join(current_path, item)

            try:
                is_dir = os.path.isdir(full_path)
                is_file = os.path.isfile(full_path)

                if is_file:
                    stat = os.stat(full_path)
                    result.append(
                        {
                            "name": item,
                            "path": full_path,
                            "type": "file",
                            "size": stat.st_size,
                        }
                    )
                elif is_dir:
                    result.append(
                        {"name": item, "path": full_path, "type": "directory"}
                    )

                    # Recurse into subdirectory
                    _walk(full_path, depth + 1)
            except OSError:
                # Skip files we can't access
                continue

        # Stop after 2000 items
        if len(result) > 2000:
            return

    _walk(path, 0)
    return result


def _check_sandbox(path: str, print_message: bool = True) -> bool:
    """Check if path is within allowed directory"""
    if Config.sandbox_disabled():
        return True

    if not path:
        return True

    # Resolve the path
    resolved_path = os.path.abspath(path)
    current_dir = os.getcwd()
    
    # Check if resolved path is within current directory
    if not (resolved_path == current_dir or resolved_path.startswith(current_dir + "/")):
        if print_message:
            print(f'[x] Sandbox: trying to access "{resolved_path}" outside current directory "{current_dir}"')
        return False
    
    return True


# Tool definition
TOOL_DEFINITION = {
    "type": "internal",
    "auto_approved": True,
    "approval_excludes_arguments": False,
    "approval_key_exclude_arguments": [],
    "hide_results": False,
    "description": "List files and directories recursively with optional pattern matching",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (defaults to current directory)",
            },
            "pattern": {
                "type": "string",
                "description": "Optional glob pattern to filter files (e.g., '*.py', 'test_*.json')",
            }
        },
        "additionalProperties": False,
    },
    "validateArguments": validateArguments,
    "formatArguments": formatArguments,
}

# Add execute method to the definition
TOOL_DEFINITION["execute"] = execute
