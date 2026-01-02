"""
Run shell command tool

"""

import subprocess
import signal
import os
import time
from typing import Dict, Any, Optional
from aicoder.core.config import Config


def execute_with_process_group(command: str, timeout: int, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """Execute command with proper process group termination"""
    # Create process group for the entire process tree
    proc = subprocess.Popen(
        command,
        shell=True,
        preexec_fn=os.setsid,  # Create new process group
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
    )
    
    try:
        # Wait for timeout with communicate
        stdout, stderr = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(
            args=command,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr
        )
        
    except subprocess.TimeoutExpired:
        # Kill entire process group (all children)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass  # Process already dead
        
        # Give it a moment to cleanup gracefully
        time.sleep(2)
        
        # Force kill if still running
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass  # Already dead
        
        # Get remaining output
        stdout, stderr = proc.communicate()
        
        return subprocess.CompletedProcess(
            args=command,
            returncode=-1,  # Custom code for timeout
            stdout=stdout,
            stderr=stderr
        )


def execute(args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute shell command with timeout"""
    command = args.get("command")
    timeout = args.get("timeout", 30)
    cwd = args.get("cwd")

    if not command:
        raise Exception("Command is required")

    try:
        # Execute command with proper process group termination
        result = execute_with_process_group(command, timeout, cwd)

        # Create friendly message
        if result.returncode == 0:
            friendly = f"✓ Command completed (exit code: {result.returncode})"
        elif result.returncode == -1:
            friendly = f"✗ Command timed out after {timeout}s (process group terminated)"
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

    # Timeout is now handled in execute_with_process_group
    # This exception should not be reached anymore
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
