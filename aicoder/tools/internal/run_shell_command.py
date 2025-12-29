"""
Run shell command tool

"""

import subprocess
from typing import Dict, Any, Optional
from aicoder.core.config import Config


def execute(args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute shell command with timeout"""
    command = args.get("command")
    timeout = args.get("timeout", 30)
    cwd = args.get("cwd")

    if not command:
        raise Exception("Command is required")

    try:
        # Execute command with UTF-8 decoding and error handling for binary output
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # Replace un-decodable bytes with � instead of failing
            timeout=timeout,
            cwd=cwd,
        )

        # Create friendly message
        if result.returncode == 0:
            friendly = f"✓ Command completed (exit code: {result.returncode})"
        elif result.returncode == 124:
            friendly = (
                f"✗ Command timed out after {timeout}s (exit code: {result.returncode})"
            )
        else:
            friendly = f"✗ Command failed (exit code: {result.returncode})"

        # Prepare output content
        output = result.stdout
        if result.stderr:
            if output:
                output += "\nSTDERR:\n" + result.stderr
            else:
                output = result.stderr

        return {
            "tool": "run_shell_command",
            "friendly": friendly,
            "detailed": f"Command: {command}\nExit code: {result.returncode}\nTimeout: {timeout}s\nWorking directory: {cwd or '.'}\n\nOutput:\n{output}"
        }

    except subprocess.TimeoutExpired:
        return {
            "tool": "run_shell_command",
            "friendly": f"✗ Command timed out after {timeout}s (exit code: 124)",
            "detailed": f"Command timed out after {timeout}s: {command}"
        }
    except Exception as e:
        return {
            "tool": "run_shell_command",
            "friendly": f"✗ Command failed: {str(e)}",
            "detailed": f"Command failed: {command}\nError: {str(e)}"
        }


# Tool definition
TOOL_DEFINITION = {
    "type": "internal",
    "auto_approved": False,  # Requires approval for safety
    "approval_excludes_arguments": False,
    "description": "Execute shell command with timeout",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 30)",
                "default": 30,
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (optional)",
                "default": None,
            },
        },
        "required": ["command"],
    },
}


def format_arguments(args):
    """Format arguments for display ()"""
    command = args.get("command")
    timeout = args.get("timeout", 30)
    reason = args.get("reason")

    lines = []
    if command:
        lines.append(f"Command: {command}")

    if reason:
        lines.append(f"Reason: {reason}")

    if timeout != 30:
        lines.append(f"Timeout: {timeout}s")

    return "\n".join(lines)


def validate_arguments(args):
    """Validate arguments"""
    command = args.get("command")
    if not command or not isinstance(command, str):
        raise Exception('run_shell_command requires "command" argument (string)')


# Add methods to the definition
TOOL_DEFINITION["execute"] = execute
TOOL_DEFINITION["formatArguments"] = format_arguments
TOOL_DEFINITION["validateArguments"] = validate_arguments
