"""
Write file tool
Following TypeScript structure exactly
"""

import os
import sys
import tempfile
from typing import Dict, Any
from aicoder.type_defs.tool_types import ToolResult, ToolPreview, ToolResult
from aicoder.core.config import Config
from aicoder.core.file_access_tracker import FileAccessTracker
from aicoder.utils.file_utils import file_exists, write_file as file_write, get_relative_path
from aicoder.utils.diff_utils import generate_unified_diff_with_status, colorize_diff


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
        print(f'[x] Sandbox: write_file trying to access "{resolved_path}" outside current directory "{current_dir}"')
        return False
    
    return True


def execute(args: Dict[str, Any]) -> ToolResult:
    """Write content to file"""
    path = args.get("path")
    content = args.get("content", "")

    if not path:
        raise Exception("Path is required")

    if not _check_sandbox(path):
        raise Exception(f'write_file: path "{path}" outside current directory not allowed')

    

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
            
            # Mark file as read since user just created/updated it
            FileAccessTracker.record_read(path)

            # Prepare result
            if exists:
                friendly = f"✓ Updated '{path}'"
            else:
                friendly = f"✓ Created '{path}' ({len(content.splitlines())} lines, {len(content)} bytes)"

            # Build friendly message
            if exists:
                friendly = f"✓ Updated '{get_relative_path(path)}'"
            else:
                friendly = (
                    f"✓ Created '{get_relative_path(path)}' "
                    f"({len(content.splitlines())} lines, {len(content)} bytes)"
                )

            # Build detailed message for AI (no diff to save context)
            detailed_parts = [
                f"Path: {path}",
                f"Action: {'Updated' if exists else 'Created'}",
                f"Size: {len(content)} bytes",
                f"Lines: {len(content.splitlines()) if content else 0}"
            ]
            
            detailed = "\n".join(detailed_parts)

            return ToolResult(
                tool="write_file",
                friendly=friendly,
                detailed=detailed
            )

        finally:
            # Cleanup temp files
            try:
                os.unlink(temp_old.name)
                os.unlink(temp_new.name)
            except:
                pass

    except Exception as e:
        return ToolResult(
            tool="write_file",
            friendly=f"❌ Error writing {get_relative_path(path)}: {str(e)}",
            detailed=(
                f"Path: {path}\n"
                f"Error: {str(e)}"
            )
        )


def generate_preview(args):
    """Generate preview for approval"""
    path = args.get("path")
    content = args.get("content", "")

    try:
        # Check if file exists
        exists = file_exists(path)
        
        # Safety check for existing files
        if exists and not FileAccessTracker.was_file_read(path):
            relative_path = get_relative_path(path)
            # Tool formats its own message (no colors - system handles display)
            safety_message = (
                f"Path: {relative_path}\n"
                "[!] Warning: The file must be read before editing."
            )
            
            return ToolPreview(
                tool="write_file",
                content=safety_message,
                can_approve=False
            )

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
            
            # Colorize diff in the tool (not system)
            colorized_diff = colorize_diff(diff_content) if diff_content else ""

            # Normal preview - format content based on file status
            if exists:
                preview_content = (
                    f"Existing file will be updated:\n\n"
                    f"{colorized_diff}"
                )
            else:
                preview_content = (
                    f"New file will be created:\n\n"
                    f"{colorized_diff}"
                )
                
            return ToolPreview(
                tool="write_file",
                content=preview_content,
                can_approve=True
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
            content=f"Error: {str(e)}",
            can_approve=False
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
