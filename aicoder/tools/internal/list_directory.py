"""
List directory tool
Following TypeScript structure exactly
"""

import os
from typing import Dict, Any, Optional
from aicoder.core.tool_formatter import ToolOutput
from aicoder.core.config import Config


def validateArguments(args: Dict[str, Any]) -> None:
    """Validate list directory arguments"""
    path = args.get("path")
    if not path or path.strip() == "":
        args["path"] = "."


def formatArguments(args: Dict[str, Any]) -> str:
    """Format arguments for approval display"""
    path = args.get("path", ".")
    if path and path != ".":
        return f"Listing directory: {path}"
    return ""


def execute(args: Dict[str, Any]) -> ToolOutput:
    """List directory contents"""
    path = args.get("path", ".")
    MAX_FILES = 100

    try:
        # Resolve path
        import os

        resolved_path = os.path.abspath(path)

        # Check sandbox restrictions
        if not _check_sandbox(resolved_path):
            return ToolOutput(
                tool="list_directory",
                friendly=f"Access denied: Path '{path}' is outside current directory",
                important={"path": path},
                results={
                    "error": f"Path '{path}' resolves outside current directory. Access denied.",
                    "showWhenDetailOff": True,
                },
            )

        # Check if path exists and is a directory
        if not os.path.exists(resolved_path) or not os.path.isdir(resolved_path):
            return ToolOutput(
                tool="list_directory",
                friendly=f"Directory not found: '{resolved_path}'",
                important={"path": path},
                results={
                    "error": f"Directory not found at '{resolved_path}'.",
                    "showWhenDetailOff": True,
                },
            )

        # Use find to list files - much faster and simpler (matching TypeScript)
        import subprocess

        find_command = f'find "{resolved_path}" -type f -print0 | head -z -n {MAX_FILES + 1} | tr "\\0" "\\n"'
        result = subprocess.run(
            find_command, shell=True, capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            raise Exception(f"find command failed: {result.stderr}")

        # Split and filter files
        files = [
            file.strip()
            for file in result.stdout.split("\n")
            if file.strip() and file.strip() != resolved_path
        ]

        actual_count = len(files)
        limited_files = files[:MAX_FILES]

        # Create output matching TypeScript structure
        if limited_files == []:
            return ToolOutput(
                tool="list_directory",
                friendly=f"Directory is empty: '{resolved_path}'",
                important={"path": path},
                results={
                    "message": f"Directory is empty: '{resolved_path}'",
                    "showWhenDetailOff": True,
                },
            )
        elif actual_count > MAX_FILES:
            return ToolOutput(
                tool="list_directory",
                friendly=f"Found {actual_count}+ files (limited to {MAX_FILES}) in '{resolved_path}'",
                important={"path": path},
                detailed={"actual_count": actual_count, "limit": MAX_FILES},
                results={"files": "\n".join(limited_files), "showWhenDetailOff": True},
            )
        else:
            return ToolOutput(
                tool="list_directory",
                friendly=f"✓ Found {actual_count} files in '{resolved_path}'",
                important={"path": path},
                detailed={"file_count": actual_count, "resolved_path": resolved_path},
                results={"files": "\n".join(limited_files), "showWhenDetailOff": True},
            )

    except Exception as e:
        return ToolOutput(
            tool="list_directory",
            friendly=f"❌ Error listing directory: {str(e)}",
            important={"path": path, "error": str(e)},
        )


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


def _check_sandbox(path: str) -> bool:
    """Check if path is within allowed directory"""
    if Config.sandbox_disabled():
        return True

    # Simple sandbox - prevent directory traversal
    if ".." in path:
        return False

    # Allow absolute paths only if they're in current directory
    if path.startswith("/"):
        cwd = os.getcwd()
        if not path.startswith(cwd):
            return False

    return True


# Tool definition matching TypeScript structure
TOOL_DEFINITION = {
    "type": "internal",
    "auto_approved": True,
    "approval_excludes_arguments": False,
    "approval_key_exclude_arguments": [],
    "hide_results": False,
    "description": "List files and directories recursively with configurable maximum",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (defaults to current directory)",
            }
        },
        "additionalProperties": False,
    },
    "validateArguments": validateArguments,
    "formatArguments": formatArguments,
}

# Add execute method to the definition
TOOL_DEFINITION["execute"] = execute
