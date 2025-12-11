"""
Write file tool
Following TypeScript structure exactly
"""

import os
import tempfile
from typing import Dict, Any
from aicoder.core.tool_formatter import ToolOutput, ToolPreview
from aicoder.core.config import Config
from aicoder.core.file_access_tracker import FileAccessTracker
from aicoder.utils.file_utils import file_exists, write_file as file_write
from aicoder.utils.diff_utils import generate_unified_diff_with_status


def execute(args: Dict[str, Any]) -> ToolOutput:
    """Write content to file"""
    path = args.get("path")
    content = args.get("content", "")

    if not path:
        raise Exception("Path is required")

    if not Config.sandbox_disabled() and ".." in path:
        raise Exception("Directory traversal not allowed")

    # Safety check: File must have been read first (tracked by FileAccessTracker)
    if file_exists(path) and not FileAccessTracker.was_file_read(path):
        return ToolOutput(
            tool="write_file",
            friendly=f"WARNING: Must read file '{path}' first before writing",
            important={"path": path},
            results={
                "error": f"Must read file first. Use read_file('{path}') before writing to avoid accidental overwrites.",
                "showWhenDetailOff": True,
            },
        )

    try:
        # Check if file exists
        exists = file_exists(path)

        # Create temporary files for diff
        temp_old = tempfile.NamedTemporaryFile(
            mode="w", suffix="_old.txt", delete=False
        )
        temp_new = tempfile.NamedTemporaryFile(
            mode="w", suffix="_new.txt", delete=False
        )

        try:
            # Write content to temp files
            if exists:
                existing_content = file_read(path)
                temp_old.write(existing_content)
            else:
                # For new files, write empty content to old file
                temp_old.write("")

            temp_new.write(content)
            temp_old.close()
            temp_new.close()

            # Generate diff
            diff_result = generate_unified_diff_with_status(
                temp_old.name, temp_new.name
            )
            diff_content = diff_result.get("diff", "")

            # Write the actual file
            file_write(path, content)

            # Prepare result
            if exists:
                friendly = f"✓ Updated '{path}'"
            else:
                friendly = f"✓ Created '{path}' ({len(content.splitlines())} lines, {len(content)} bytes)"

            return ToolOutput(
                tool="write_file",
                friendly=friendly,
                important={
                    "path": path,
                    "exists": exists,
                    "size": len(content),
                    "lines": len(content.splitlines()) if content else 0,
                },
                detailed={
                    "content_length": len(content),
                    "lines": len(content.splitlines()) if content else 0,
                    "diff": diff_content,
                },
            )

        finally:
            # Cleanup temp files
            try:
                os.unlink(temp_old.name)
                os.unlink(temp_new.name)
            except:
                pass

    except Exception as e:
        return ToolOutput(
            tool="write_file",
            friendly=f"❌ Error writing {path}: {str(e)}",
            important={"path": path, "error": str(e)},
        )


def generate_preview(args):
    """Generate preview for approval"""
    path = args.get("path")
    content = args.get("content", "")

    try:
        # Check if file exists
        exists = file_exists(path)
        
        # Add warning if file exists but wasn't read first
        warning = None
        if exists and not FileAccessTracker.was_file_read(path):
            warning = "File exists but was not read first - potential overwrite"

        # Create temporary files for diff
        temp_old = tempfile.NamedTemporaryFile(
            mode="w", suffix="_old.txt", delete=False
        )
        temp_new = tempfile.NamedTemporaryFile(
            mode="w", suffix="_new.txt", delete=False
        )

        try:
            # Write content to temp files
            if exists:
                existing_content = file_read(path)
                temp_old.write(existing_content)
            else:
                # For new files, write empty content to old file
                temp_old.write("")

            temp_new.write(content)
            temp_old.close()
            temp_new.close()

            # Generate diff
            diff_result = generate_unified_diff_with_status(
                temp_old.name, temp_new.name
            )
            diff_content = diff_result.get("diff", "")

            return ToolPreview(
                tool="write_file",
                summary=f"{'Modify existing file' if exists else 'Create new file'}: {path}",
                content=diff_content,
                can_approve=False if warning else True,  # Don't allow approval if warning exists
                is_diff=True,
                warning=warning,
            )

        finally:
            # Cleanup temp files
            try:
                os.unlink(temp_old.name)
                os.unlink(temp_new.name)
            except:
                pass

    except Exception as e:
        return ToolPreview(
            tool="write_file",
            summary=f"Error: {str(e)}",
            content="",
            can_approve=False,
            warning=str(e),
        )


def format_arguments(args):
    """Format arguments for display"""
    path = args.get("path", "")
    content = args.get("content", "")

    lines = [f"Path: {path}"]

    # Show content preview
    if len(content) > 100:
        content_preview = content[:100] + f"... ({len(content)} chars total)"
    else:
        content_preview = content

    lines.append(f"Content: {content_preview}")
    return "\n  ".join(lines)


def validate_arguments(args):
    """Validate arguments"""
    path = args.get("path")
    content = args.get("content")

    if not path or not isinstance(path, str):
        raise Exception('write_file requires "path" argument (string)')
    if content is None:
        raise Exception('write_file requires "content" argument')


def file_read(path: str) -> str:
    """Read file content"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# Tool definition matching TypeScript structure
TOOL_DEFINITION = {
    "type": "internal",
    "auto_approved": False,  # Requires approval for safety
    "approval_excludes_arguments": False,
    "description": "Writes complete content to a file, creating directories as needed.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file system path where to write the content.",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file.",
            },
        },
        "required": ["path", "content"],
    },
}

# Add methods to the definition
TOOL_DEFINITION["execute"] = execute
TOOL_DEFINITION["formatArguments"] = format_arguments
TOOL_DEFINITION["validateArguments"] = validate_arguments
TOOL_DEFINITION["generatePreview"] = generate_preview
