"""
Edit file tool
Following TypeScript structure exactly
"""

import os
import tempfile
from typing import Dict, Any, List, Tuple
from aicoder.core.tool_formatter import ToolOutput, ToolPreview
from aicoder.core.config import Config
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


def execute(args: Dict[str, Any]) -> ToolOutput:
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

    try:
        content = read_file(path)

        if old_string not in content:
            return ToolOutput(
                tool="edit_file",
                friendly=f"❌ Text not found in {path}: '{old_string[:50]}{'...' if len(old_string) > 50 else ''}'",
                important={
                    "path": path,
                    "old_string": old_string,
                    "action": "not_found",
                },
                detailed={"error": "Text not found"},
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

        # Prepare friendly message matching TypeScript exactly
        if new_string is None or new_string == "":
            friendly = (
                f"✓ Deleted content from '{path}' ({len(old_string)} chars removed)"
            )
        else:
            friendly = (
                f"✓ Updated '{path}' ({len(old_string)} → {len(new_string)} chars)"
            )

        return ToolOutput(
            tool="edit_file",
            friendly=friendly,
            important={
                "path": path,
                "action": "replaced" if new_string else "deleted",
                "old_length": len(old_string),
                "new_length": len(new_string) if new_string else 0,
                "file_size_change": len(new_content) - len(content),
                "occurrences": occurrences,
            },
            detailed={"diff": "".join(diff_lines), "occurrences": occurrences},
        )

    except Exception as e:
        return ToolOutput(
            tool="edit_file",
            friendly=f"❌ Error editing {path}: {str(e)}",
            important={"path": path, "error": str(e)},
        )


def generate_preview(args):
    """Generate preview for approval"""
    path = args.get("path")
    old_string = args.get("old_string")
    new_string = args.get("new_string")

    if not path or old_string is None:
        return ToolPreview(
            tool="edit_file",
            summary="Missing required arguments",
            content="",
            can_approve=False,
        )

    try:
        if not _check_sandbox(path):
            raise Exception(f"Access denied: {path}")

        if not file_exists(path):
            raise Exception(f"File not found: {path}")

        content = read_file(path)

        if old_string not in content:
            return ToolPreview(
                tool="edit_file",
                summary=f"Text not found in {path}",
                content=f"Error: '{old_string[:50]}{'...' if len(old_string) > 50 else ''}' not found",
                can_approve=False,
                warning="Text to edit not found in file",
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
            diff_content = diff_result.get("diff", "")

            return ToolPreview(
                tool="edit_file",
                summary=f"Edit {path}",
                content=diff_content,
                can_approve=True,
                is_diff=True,
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
            tool="edit_file",
            summary=f"Error: {str(e)}",
            content="",
            can_approve=False,
            warning=str(e),
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
