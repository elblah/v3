"""
Read file tool

"""

import os
from typing import Dict, Any
from aicoder.core.config import Config
from aicoder.core.file_access_tracker import FileAccessTracker
from aicoder.utils.file_utils import file_exists, read_file as file_read, check_sandbox
from aicoder.utils.log import LogUtils

# Configuration
DEFAULT_READ_LIMIT = Config.default_read_limit()
MAX_LINE_LENGTH = 2000  # truncate single lines longer than this (minified files etc.)

# Plugin system reference (set at startup by ToolManager)
_plugin_system = None


def set_plugin_system(plugin_system) -> None:
    """Set plugin system reference (for on_read_file intercept hooks)"""
    global _plugin_system
    _plugin_system = plugin_system


def _get_virtual_content(path: str):
    """
    Query on_read_file hooks for virtual content (internal skills etc.).

    Intercept hooks REPLACE the tool result (unlike observing hooks):
    first hook returning a str (even empty) supplies the content INSTEAD of
    the real file. None (or non-str) = "not my path", fall through.
    Fires BEFORE sandbox/file_exists — virtual paths live outside cwd.
    """
    if not _plugin_system:
        return None

    results = _plugin_system.call_hooks("on_read_file", path)
    if not results:
        return None

    for result in results:
        if isinstance(result, str):
            return result
    return None


def _paginate(path: str, offset: int, limit: int, content: str) -> Dict[str, Any]:
    """Build the read_file result dict from raw content"""
    lines = content.split("\n")

    # Apply offset and limit
    if offset >= len(lines):
        return {
            "tool": "read_file",
            "friendly": f"File {path} has {len(lines)} lines, but offset {offset} is beyond end of file",
            "detailed": f"Cannot read file '{path}'. Requested offset {offset} but file only has {len(lines)} lines."
        }

    end_index = min(offset + limit, len(lines))
    selected_lines = lines[offset:end_index]
    # Truncate very long lines (minified JS etc.) to protect context window
    truncated_lines = [
        line if len(line) <= MAX_LINE_LENGTH else line[:MAX_LINE_LENGTH] + f"... ({len(line)} chars total)"
        for line in selected_lines
    ]
    selected_content = "\n".join(truncated_lines)

    friendly_msg = f"Read {len(selected_lines)} lines from {path}"
    if offset > 0 or end_index < len(lines):
        friendly_msg += f" (showing lines {offset + 1}-{end_index} of {len(lines)})"

    return {
        "tool": "read_file",
        "friendly": friendly_msg,
        "detailed": f"File: {path}\nTotal lines: {len(lines)}\nShowing: lines {offset + 1}-{end_index}\n\nContent:\n{selected_content}"
    }


def execute(args: Dict[str, Any]) -> Dict[str, Any]:
    """Read file with pagination"""
    path = args.get("path")
    try:
        offset = int(args.get("offset", 0))
    except ValueError:
        raise Exception("offset must be an integer, got: " + str(args.get("offset")))
    
    try:
        limit = int(args.get("limit", DEFAULT_READ_LIMIT))
    except ValueError:
        raise Exception("limit must be an integer, got: " + str(args.get("limit")))

    if not path:
        raise Exception("Path is required")

    # Virtual content (internal skills, plugin-served files) — before sandbox
    # and file_exists: virtual paths don't exist on disk and live outside cwd.
    virtual = _get_virtual_content(path)
    if virtual is not None:
        return _paginate(path, offset, limit, virtual)

    if not check_sandbox(path, "read_file"):
        resolved_path = os.path.abspath(path)
        current_dir = os.getcwd()
        raise Exception(f'Path: {path}\n[x] Sandbox: trying to access "{resolved_path}" outside current directory "{current_dir}"')

    if not file_exists(path):
        raise Exception(f"File not found: {path}")

    try:
        content = file_read(path)
        
        # Record that this file was read for safety tracking
        FileAccessTracker.record_read(path)

        return _paginate(path, offset, limit, content)

    except Exception as e:
        return {
            "tool": "read_file",
            "friendly": f"❌ Error reading {path}: {str(e)}",
            "detailed": f"Error reading file '{path}': {str(e)}"
        }


def generatePreview(args):
    """Generate preview with sandbox validation (executed BEFORE approval)"""
    path = args.get("path", "")

    # Virtual files need no preview — content is served by plugins
    if _get_virtual_content(path) is not None:
        return None

    # Check sandbox first - don't print message since preview will show it
    if not check_sandbox(path, "read_file", print_message=False):
        import os.path

        resolved_path = os.path.abspath(path)
        current_dir = os.getcwd()

        return {
            "tool": "read_file",
            "content": f'Path: {path}\n[x] Sandbox: trying to access "{resolved_path}" outside current directory "{current_dir}"',
            "can_approve": False,
        }

    # If sandbox passes, no preview needed
    return None


def format_arguments(args):
    """Format arguments for display"""
    path = args.get("path")
    offset = args.get("offset", 0)
    limit = args.get("limit", DEFAULT_READ_LIMIT)

    lines = [f"Path: {path}"]

    if offset != 0:
        lines.append(f"Offset: {offset}")

    if limit != DEFAULT_READ_LIMIT:
        lines.append(f"Limit: {limit}")

    return "\n  ".join(lines)


def validate_arguments(args):
    """Validate arguments"""
    path = args.get("path")
    if not path or not isinstance(path, str):
        raise Exception('read_file requires "path" argument (string)')


# Tool definition
TOOL_DEFINITION = {
    "type": "internal",
    "auto_approved": True,
    "approval_excludes_arguments": False,
    "description": "Reads the content from a specified file path.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The file system path to read from.",
            },
            "offset": {
                "type": "integer",
                "description": "The line number to start reading from (default: 0).",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": f"The number of lines to read (default: {DEFAULT_READ_LIMIT}, can be increased to read more).",
                "default": DEFAULT_READ_LIMIT,
            },
        },
        "required": ["path"],
    },
}

# Add methods to the definition
TOOL_DEFINITION["execute"] = execute
TOOL_DEFINITION["formatArguments"] = format_arguments
TOOL_DEFINITION["validateArguments"] = validate_arguments
TOOL_DEFINITION["generatePreview"] = generatePreview
