"""
List directory tool

"""

import fnmatch
import os
from typing import Dict, Any
from aicoder.core.config import Config
from aicoder.utils.file_utils import check_sandbox, open_directory_verified


def _matches_pattern(filename: str, pattern: str) -> bool:
    """True if filename matches the user glob. '**' is treated as zero+ dirs,
    so '**/*.py' degrades to a plain '*\\.py' match."""
    clean_pattern = pattern.replace("**/", "")
    return fnmatch.fnmatch(filename, clean_pattern)


def validateArguments(args: Dict[str, Any]) -> None:
    """Validate list directory arguments"""
    path = args.get("path")
    if not path or path.strip() == "":
        args["path"] = "."
    max_depth = args.get("max_depth")
    if not max_depth or max_depth < 1:
        args["max_depth"] = 1


def formatArguments(args: Dict[str, Any]) -> str:
    """Format arguments for approval display"""
    path = args.get("path", ".")
    pattern = args.get("pattern")
    depth = args.get("max_depth", 1)
    if pattern:
        return f"Listing '{path}' matching: {pattern} (depth {depth})"
    if path and path != ".":
        return f"Listing directory: {path} (depth {depth})"
    return f"Listing current dir (depth {depth})" if depth > 1 else ""


def execute(args: Dict[str, Any]) -> Dict[str, Any]:
    """List directory contents using os.walk with ignore dir filtering"""
    path = args.get("path", ".")
    pattern = args.get("pattern")
    max_depth = args.get("max_depth", 1)
    MAX_FILES = 100

    try:
        # Resolve path
        resolved_path = os.path.abspath(path)

        # Check sandbox restrictions (friendly static check; races are
        # additionally blocked by the verified opens below)
        if not check_sandbox(resolved_path, "list_directory", print_message=False):
            sandbox_msg = f'Path: {path}\n[x] Sandbox: trying to access "{resolved_path}" outside current directory "{os.getcwd()}"'
            return {
                "tool": "list_directory",
                "friendly": sandbox_msg,
                "detailed": sandbox_msg
            }

        # Entry point: open the directory TOCTOU-safe; we list what this fd
        # actually points at, so a raced symlink swap cannot escape.
        try:
            root_fd = open_directory_verified(resolved_path, "list_directory")
        except (FileNotFoundError, NotADirectoryError):
            return {
                "tool": "list_directory",
                "friendly": f"Directory not found: '{resolved_path}'",
                "detailed": f"Directory not found at '{resolved_path}'. Path does not exist or is not a directory."
            }

        # Get directories and patterns to ignore
        ignore_dirs = set(Config.ignore_dirs())
        ignore_patterns = Config.ignore_patterns()

        files = []

        def _walk_with_depth(dir_fd, rel, depth):
            # Scandir from an already-proven dirfd; subdirs are descended by
            # reopening their *lexical* path through open_directory_verified, which is
            # kernel-proven in-bounds (openat2 RESOLVE_BENEATH) and
            # fail-closed on any raced symlink/traversal swap.
            if depth >= max_depth:
                return
            try:
                entries = list(os.scandir(dir_fd))
            except OSError:
                return

            for entry in entries:
                # Compute the verified descendant path (fd-relative + root)
                child_rel = rel + [entry.name]
                child_full = os.path.join(resolved_path, *child_rel)
                if entry.is_file():
                    # Check pattern (only when a filter was requested)
                    if pattern is not None and not _matches_pattern(
                        entry.name, pattern
                    ):
                        continue
                    # Check ignore patterns
                    if any(entry.name.endswith(p) for p in ignore_patterns):
                        continue
                    # Check ignore dirs
                    if any(part in ignore_dirs for part in child_rel):
                        continue
                    files.append(child_full)
                    if len(files) >= MAX_FILES + 1:
                        return
                elif entry.is_dir():
                    # Check ignore dirs
                    if entry.name in ignore_dirs:
                        continue
                    if entry.name.startswith("."):
                        continue
                    # Check pattern - list dir if it matches (only when a filter
                    # was requested; without one, list every dir for recursion)
                    if pattern is not None and _matches_pattern(entry.name, pattern):
                        files.append(child_full)
                        if len(files) >= MAX_FILES + 1:
                            return
                    # Always recurse into dirs via a verified child fd
                    try:
                        sub_fd = open_directory_verified(child_full, "list_directory")
                    except OSError:
                        continue
                    try:
                        _walk_with_depth(sub_fd, child_rel, depth + 1)
                        if len(files) >= MAX_FILES + 1:
                            return
                    finally:
                        os.close(sub_fd)

        try:
            _walk_with_depth(root_fd, [], 0)
        finally:
            os.close(root_fd)

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
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum directory depth to list (default: 1 = current level only). max_depth=2 includes one level of subdirectories, etc.",
                "default": 1
            }
        },
        "additionalProperties": False,
    },
    "validateArguments": validateArguments,
    "formatArguments": formatArguments,
}

# Add execute method to the definition
TOOL_DEFINITION["execute"] = execute
