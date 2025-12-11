"""
List directory tool
Following TypeScript structure exactly
"""

import os
from typing import Dict, Any, Optional
from aicoder.type_defs.tool_types import ToolResult
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


def execute(args: Dict[str, Any]) -> ToolResult:
    """List directory contents"""
    path = args.get("path", ".")
    MAX_FILES = 100

    try:
        # Resolve path
        import os

        resolved_path = os.path.abspath(path)

        # Check sandbox restrictions
        if not _check_sandbox(resolved_path):
            # The sandbox message is already printed by _check_sandbox
            return ToolResult(
                tool="list_directory",
                friendly=f'list_directory: path "{path}" outside current directory not allowed',
                detailed=f'list_directory: path "{path}" outside current directory not allowed'
            )

        # Check if path exists and is a directory
        if not os.path.exists(resolved_path) or not os.path.isdir(resolved_path):
            return ToolResult(
                tool="list_directory",
                friendly=f"Directory not found: '{resolved_path}'",
                detailed=f"Directory not found at '{resolved_path}'. Path does not exist or is not a directory."
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
            return ToolResult(
                tool="list_directory",
                friendly=f"Directory is empty: '{resolved_path}'",
                detailed=f"Directory '{resolved_path}' exists but contains no files or subdirectories."
            )
        elif actual_count > MAX_FILES:
            return ToolResult(
                tool="list_directory",
                friendly=f"Found {actual_count}+ files (limited to {MAX_FILES}) in '{resolved_path}'",
                detailed=f"Directory contains {actual_count} items total. Showing first {MAX_FILES}:\n\n{chr(10).join(limited_files)}"
            )
        else:
            return ToolResult(
                tool="list_directory",
                friendly=f"✓ Found {actual_count} files in '{resolved_path}'",
                detailed=f"Directory '{resolved_path}' contents ({actual_count} items):\n\n{chr(10).join(limited_files)}"
            )

    except Exception as e:
        return ToolResult(
            tool="list_directory",
            friendly=f"❌ Error listing directory: {str(e)}",
            detailed=f"Error listing directory '{path}': {str(e)}"
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
            print(f'[x] Sandbox: list_directory trying to access "{resolved_path}" outside current directory "{current_dir}"')
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
