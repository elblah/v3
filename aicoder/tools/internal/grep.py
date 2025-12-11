"""
Grep tool - text search in files
Following TypeScript structure exactly
"""

import os
import subprocess
from typing import Dict, Any, Optional
from aicoder.core.tool_formatter import ToolOutput
from aicoder.core.config import Config


def validateArguments(args: Dict[str, Any]) -> None:
    """Validate grep arguments"""
    pattern = args.get("text")
    if not pattern or not isinstance(pattern, str):
        raise Exception('grep requires "text" argument (string)')


def formatArguments(args: Dict[str, Any]) -> str:
    """Format arguments for approval display"""
    text = args.get("text", "")
    path = args.get("path", ".")
    max_results = args.get("max_results", 2000)
    context = args.get("context", 2)

    parts = [f'Text: "{text}"']
    if path and path != ".":
        parts.append(f"Path: {path}")
    if max_results != 2000:
        parts.append(f"Max results: {max_results}")
    if context != 2:
        parts.append(f"Context: {context} lines")

    return "\n  ".join(parts)


def execute(args: Dict[str, Any]) -> ToolOutput:
    """Search for text in files using ripgrep or grep"""
    text = args.get("text")
    path = args.get("path", ".")
    max_results = args.get("max_results", 2000)
    context = args.get("context", 2)

    if not text:
        raise Exception("Text is required")

    try:
        # Check sandbox restrictions
        if not _check_sandbox(path):
            return ToolOutput(
                tool="grep",
                friendly=f'ERROR: Failed to search: path "{path}" outside current directory not allowed',
                important={"text": text},
                results={
                    "error": f'path "{path}" outside current directory not allowed',
                    "showWhenDetailOff": True,
                },
            )

        # Validate search text
        if not text.strip():
            return ToolOutput(
                tool="grep",
                important={"text": text},
                results={
                    "error": "Search text cannot be empty.",
                    "showWhenDetailOff": True,
                },
            )

        # Build command using ripgrep (matching TypeScript exactly)
        import os

        search_path = os.path.abspath(path)

        cmd = [
            "rg",
            "-n",  # Line numbers
            "--max-count",
            str(max_results),
            "-C",
            str(context),  # Context lines
            text,
            search_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        # Parse results
        matches = result.stdout.strip().split("\n") if result.stdout.strip() else []

        # Create friendly message
        if not matches:
            friendly = f"🔍 No matches found for '{text}'"
        else:
            friendly = f"🔍 Found {len(matches)} matches for '{text}'"

        return ToolOutput(
            tool="grep",
            friendly=friendly,
            important={
                "text": text,
                "path": path,
                "matches_found": len(matches),
                "max_results": max_results,
                "context": context,
                "tool_used": "ripgrep",
            },
            results={"matches": matches, "command": " ".join(cmd)},
        )

    except subprocess.TimeoutExpired:
        return ToolOutput(
            tool="grep",
            friendly=f"⏰ Search timed out",
            important={"text": text, "error": "timeout"},
        )
    except Exception as e:
        return ToolOutput(
            tool="grep",
            friendly=f"❌ Search error: {str(e)}",
            important={"text": text, "error": str(e)},
        )


def _has_ripgrep() -> bool:
    """Check if ripgrep is available"""
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True)
        return True
    except:
        return False


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
    "description": "Search text in files using ripgrep with line numbers. Path defaults to current directory.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to search for."},
            "path": {
                "type": "string",
                "description": "Directory path to search in (defaults to current directory).",
            },
            "max_results": {
                "type": "number",
                "description": "Maximum number of results (defaults to 2000).",
            },
            "context": {
                "type": "number",
                "description": "Number of lines to show before/after match (defaults to 2).",
            },
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    "validateArguments": validateArguments,
    "formatArguments": formatArguments,
}

# Add execute method to the definition
TOOL_DEFINITION["execute"] = execute
