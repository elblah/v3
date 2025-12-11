"""
Edit file tool
Following TypeScript structure exactly
"""

import os
import tempfile
from typing import Dict, Any, List, Tuple
from aicoder.type_defs.tool_types import ToolResult, ToolPreview
from aicoder.core.config import Config
from aicoder.core.file_access_tracker import FileAccessTracker
from aicoder.utils.file_utils import file_exists, read_file, write_file
from aicoder.utils.diff_utils import generate_unified_diff_with_status


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


def _find_occurrences(content: str, old_string: str) -> List[int]:
    """Find all occurrences of old_string in content"""
    if not old_string:
        return []

    occurrences = []
    start = 0
    while True:
        pos = content.find(old_string, start)
        if pos == -1:
            break
        occurrences.append(pos)
        start = pos + 1

    return occurrences


def execute(args: Dict[str, Any]) -> ToolResult:
    """Edit file by replacing text"""
    path = args.get("path")
    old_string = args.get("old_string")
    new_string = args.get("new_string")

    if not path or old_string is None:
        raise Exception("Path and old_string are required")

    if not _check_sandbox(path):
        raise Exception(f"Access denied: {path}")

    if not file_exists(path):
        raise Exception(f"File not found: {path}")

    # Safety check: File must have been read first (tracked by FileAccessTracker)
    if not FileAccessTracker.was_file_read(path):
        return ToolResult(
            tool="edit_file",
            friendly=f"WARNING: Must read file '{path}' first before editing",
            detailed=f"Must read file first. Use read_file('{path}') before editing."
        )

    try:
        content = read_file(path)

        if old_string not in content:
            from aicoder.utils.file_utils import get_relative_path
            relative_path = get_relative_path(path)
            return ToolResult(
                tool="edit_file",
                friendly=f"ERROR: Text not found in '{relative_path}' - check exact match including whitespace",
                detailed=f"old_string not found in file. Use read_file('{relative_path}') to see current content and ensure exact match."
            )

        # Create temp files for diff preview
        temp_old = tempfile.NamedTemporaryFile(
            mode="w", suffix="_old.txt", delete=False
        )
        temp_new = tempfile.NamedTemporaryFile(
            mode="w", suffix="_new.txt", delete=False
        )

        try:
            temp_old.write(content)
            new_content = content.replace(old_string, new_string or "")
            temp_new.write(new_content)
            temp_old.close()
            temp_new.close()

            # Generate diff
            diff_result = generate_unified_diff_with_status(
                temp_old.name, temp_new.name
            )
            diff_lines = diff_result.get("diff", "").split("\n")

        finally:
            # Cleanup temp files
            try:
                os.unlink(temp_old.name)
                os.unlink(temp_new.name)
            except:
                pass

        # Count occurrences
        occurrences = len(_find_occurrences(content, old_string))

        # Write the new content
        write_file(path, new_content)
        
        # Mark file as read since user just modified it
        FileAccessTracker.record_read(path)

        # Prepare friendly message matching TypeScript exactly
        if new_string is None or new_string == "":
            friendly = (
                f"✓ Deleted content from '{path}' ({len(old_string)} chars removed)"
            )
        else:
            friendly = (
                f"✓ Updated '{path}' ({len(old_string)} → {len(new_string)} chars)"
            )

        return ToolResult(
            tool="edit_file",
            friendly=friendly,
            detailed=f"Edit completed: {friendly}"
        )

    except Exception as e:
        return ToolResult(
            tool="edit_file",
            friendly=f"❌ Error editing {path}: {str(e)}",
            detailed=f"Error editing file '{path}': {str(e)}"
        )


def generate_preview(args):
    """Generate preview for approval"""
    path = args.get("path")
    old_string = args.get("old_string")
    new_string = args.get("new_string")

    if not path or old_string is None:
        msg = []
        if not path:
            msg.append("- path is required")
        if old_string is None:
            msg.append("- old_string is required")
        return ToolPreview(
            tool="edit_file",
            content=f"Error: Missing required arguments:\n" + "\n".join(msg),
            can_approve=False,
        )

    try:
        from aicoder.utils.file_utils import get_relative_path
        relative_path = get_relative_path(path)
        
        if not _check_sandbox(path):
            return ToolPreview(
                tool="edit_file",
                content=f"Path: {relative_path}\nError: Access denied - path is outside allowed directory",
                can_approve=False,
            )

        if not file_exists(path):
            return ToolPreview(
                tool="edit_file",
                content=f"Path: {relative_path}\nError: File not found",
                can_approve=False,
            )

        content = read_file(path)

        if old_string not in content:
            from aicoder.utils.file_utils import get_relative_path
            relative_path = get_relative_path(path)
            return ToolPreview(
                tool="edit_file",
                content=f"Path: {relative_path}\nError: old_string not found in file. Use read_file('{relative_path}') to see current content and ensure exact match.",
                can_approve=False,
            )

        # Safety check for file reads
        can_approve = True
        warning = None
        safety_violation_content = None
        
        if not FileAccessTracker.was_file_read(path):
            from aicoder.utils.file_utils import get_relative_path
            relative_path = get_relative_path(path)
            can_approve = False
            warning = "File was not read first - recommend reading file before editing"
            safety_violation_content = f"Path: {relative_path}\n[!] Warning: Must read file first before editing to prevent accidental overwrites."

        # Create temp files for diff preview
        temp_old = tempfile.NamedTemporaryFile(
            mode="w", suffix="_old.txt", delete=False
        )
        temp_new = tempfile.NamedTemporaryFile(
            mode="w", suffix="_new.txt", delete=False
        )

        try:
            temp_old.write(content)
            new_content = content.replace(old_string, new_string or "")
            temp_new.write(new_content)
            temp_old.close()
            temp_new.close()

            # Generate diff
            diff_result = generate_unified_diff_with_status(
                temp_old.name, temp_new.name
            )
            diff_content = diff_result.get("diff", "")
            
            # Colorize the diff and remove headers
            from aicoder.utils.file_utils import get_relative_path
            relative_path = get_relative_path(path)
            if can_approve:
                # Normal case: show colored diff with path before approval
                from aicoder.utils.diff_utils import colorize_diff
                colorized_diff = colorize_diff(diff_content)
                
                # Combine path and colored diff for preview
                preview_content = f"Path: {relative_path}\n\n{colorized_diff}"
            else:
                # Safety violation: already contains path and warning
                preview_content = safety_violation_content

            return ToolPreview(
                tool="edit_file",
                content=preview_content,
                can_approve=can_approve,
            )

        finally:
            # Cleanup temp files
            try:
                os.unlink(temp_old.name)
                os.unlink(temp_new.name)
            except:
                pass

    except Exception as e:
        from aicoder.utils.file_utils import get_relative_path
        path = args.get('path', 'unknown')
        relative_path = get_relative_path(path) if path != 'unknown' else 'unknown'
        return ToolPreview(
            tool="edit_file",
            content=f"Path: {relative_path}\nError: {str(e)}",
            can_approve=False,
        )


def format_arguments(args):
    """Format arguments for display"""
    path = args.get("path")
    old_string = args.get("old_string")
    new_string = args.get("new_string")

    lines = [f"Path: {path}"]

    if old_string is not None:
        old_preview = old_string[:50] + ("..." if len(old_string) > 50 else "")
        lines.append(f"Old: {old_preview}")

    if new_string is not None:
        new_preview = new_string[:50] + ("..." if len(new_string) > 50 else "")
        lines.append(f"New: {new_preview}")

    return "\n  ".join(lines)


def validate_arguments(args):
    """Validate arguments"""
    path = args.get("path")
    old_string = args.get("old_string")

    if not path or not isinstance(path, str):
        raise Exception('edit_file requires "path" argument (string)')
    if old_string is None:
        raise Exception('edit_file requires "old_string" argument')


# Tool definition matching TypeScript structure
TOOL_DEFINITION = {
    "type": "internal",
    "auto_approved": False,  # Requires approval for safety
    "approval_excludes_arguments": False,
    "description": "Edits a file by replacing exact text matches.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit"},
            "old_string": {
                "type": "string",
                "description": "Text to replace (exact match required)",
            },
            "new_string": {
                "type": "string",
                "description": "New text to insert (deletes if empty or omitted)",
            },
        },
        "required": ["path", "old_string"],
    },
}

# Add methods to the definition
TOOL_DEFINITION["execute"] = execute
TOOL_DEFINITION["formatArguments"] = format_arguments
TOOL_DEFINITION["validateArguments"] = validate_arguments
TOOL_DEFINITION["generatePreview"] = generate_preview
