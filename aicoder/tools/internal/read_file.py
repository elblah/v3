"""
Read file tool
Following TypeScript structure exactly
"""

import os
from typing import Dict, Any
from aicoder.type_defs.tool_types import ToolResult, ToolPreview
from aicoder.core.config import Config
from aicoder.core.file_access_tracker import FileAccessTracker
from aicoder.utils.file_utils import file_exists, read_file as file_read

DEFAULT_READ_LIMIT = 2000
MAX_LINE_LENGTH = 2000


def _check_sandbox(path: str) -> bool:
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
        print(f'[x] Sandbox: read_file trying to access "{resolved_path}" outside current directory "{current_dir}"')
        return False
    
    return True


def execute(args: Dict[str, Any]) -> ToolResult:
    """Read file with pagination"""
    path = args.get("path")
    offset = args.get("offset", 0)
    limit = args.get("limit", DEFAULT_READ_LIMIT)

    if not path:
        raise Exception("Path is required")

    if not _check_sandbox(path):
        resolved_path = os.path.abspath(path)
        current_dir = os.getcwd()
        raise Exception(f'read_file: path "{path}" outside current directory not allowed')

    if not file_exists(path):
        raise Exception(f"File not found: {path}")

    try:
        content = file_read(path)
        
        # Record that this file was read for safety tracking
        FileAccessTracker.record_read(path)
        
        lines = content.split("\n")

        # Apply offset and limit
        if offset >= len(lines):
            return ToolResult(
                tool="read_file",
                friendly=f"File {path} has {len(lines)} lines, but offset {offset} is beyond end of file",
                detailed=f"Cannot read file '{path}'. Requested offset {offset} but file only has {len(lines)} lines."
            )

        end_index = min(offset + limit, len(lines))
        selected_lines = lines[offset:end_index]
        selected_content = "\n".join(selected_lines)

        # Count lines for each line (limit line length)
        line_info = []
        for i, line in enumerate(selected_lines, start=offset):
            truncated = False
            if len(line) > MAX_LINE_LENGTH:
                line = line[:MAX_LINE_LENGTH] + f"... ({len(line)} chars total)"
                truncated = True
            line_info.append((i, line, truncated))

        # Format the result
        formatted_lines = []
        for line_num, line_content, was_truncated in line_info:
            if was_truncated:
                formatted_lines.append(f"[{line_num}] {line_content}")
            else:
                formatted_lines.append(f"[{line_num}] {line_content}")

        formatted_content = "\n".join(formatted_lines)

        friendly_msg = f"Read {len(selected_lines)} lines from {path}"
        if offset > 0 or end_index < len(lines):
            friendly_msg += f" (showing lines {offset + 1}-{end_index} of {len(lines)})"

        return ToolResult(
            tool="read_file",
            friendly=friendly_msg,
            detailed=f"File: {path}\nTotal lines: {len(lines)}\nShowing: lines {offset + 1}-{end_index}\n\nContent:\n{selected_content}"
        )

    except Exception as e:
        return ToolResult(
            tool="read_file",
            friendly=f"❌ Error reading {path}: {str(e)}",
            detailed=f"Error reading file '{path}': {str(e)}"
        )


def generatePreview(args):
    """Generate preview with sandbox validation (executed BEFORE approval)"""
    path = args.get("path", "")

    # Check sandbox first - this generates the nice warning message
    if not _check_sandbox(path):
        from aicoder.core.tool_formatter import ToolPreview
        
        resolved_path = os.path.abspath(path)
        current_dir = os.getcwd()
        
        return ToolPreview(
            tool="read_file",
            content=f'[x] Sandbox: read_file trying to access "{resolved_path}" outside current directory "{current_dir}"',
            can_approve=False,
        )

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


# Tool definition matching TypeScript structure
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
                "description": f"The number of lines to read (default: {DEFAULT_READ_LIMIT}).",
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
