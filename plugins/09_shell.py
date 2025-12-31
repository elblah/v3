"""
Shell Plugin - Execute shell commands

Features:
- Direct command execution via /shell command
- Tool for AI to run shell commands
- Useful for checking current directory (pwd), file operations, etc.

Commands:
- /shell <command> - Execute a shell command directly

Tools:
- shell_exec - Execute shell commands (for AI use)
"""

import subprocess
import os
from typing import Dict, Any


def create_plugin(ctx):
    """Shell command execution plugin"""

    DEFAULT_TIMEOUT = 30
    DEFAULT_CWD = None  # Uses current working directory

    def execute_shell(command: str, timeout: int = DEFAULT_TIMEOUT, cwd: str = DEFAULT_CWD) -> str:
        """Execute a shell command and return output"""
        if not command or not command.strip():
            return "Error: Command cannot be empty"

        try:
            # Resolve cwd
            resolved_cwd = cwd if cwd else os.getcwd()

            # Run command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=resolved_cwd
            )

            # Combine stdout and stderr
            output = []
            if result.stdout:
                output.append(result.stdout)
            if result.stderr:
                output.append(f"[stderr]\n{result.stderr}")

            # Add exit code if non-zero
            if result.returncode != 0:
                output.append(f"\n[exit code: {result.returncode}]")

            return "\n".join(output) if output else "[no output]"

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds"
        except FileNotFoundError:
            return f"Error: Working directory not found: {cwd}"
        except Exception as e:
            return f"Error executing command: {e}"

    def handle_shell_command(args_str: str) -> str:
        """
        Handle /shell command

        Usage:
            /shell pwd                    - Show current directory
            /shell ls -la                 - List files
            /shell cp file.txt /mnt/      - Copy file
            /shell <any command>          - Execute any shell command
        """
        if not args_str or not args_str.strip():
            return """Shell Plugin

Execute shell commands directly.

Usage:
    /shell <command>

Examples:
    /shell pwd              - Show current working directory
    /shell ls -la           - List files in current directory
    /shell cp file.txt /mnt/ - Copy file to /mnt/
    /shell whoami           - Show current user
    /shell date             - Show current date/time

Note: Commands are executed with a 30-second timeout.
"""

        command = args_str.strip()
        output = execute_shell(command, DEFAULT_TIMEOUT)
        return output

    def shell_exec(args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tool for AI to execute shell commands

        Parameters:
            command (required): Shell command to execute
            timeout (optional): Timeout in seconds (default: 30)
            cwd (optional): Working directory (default: current dir)
        """
        command = args.get("command", "")
        timeout = args.get("timeout", DEFAULT_TIMEOUT)
        cwd = args.get("cwd", None)

        if not command:
            return {
                "tool": "shell_exec",
                "friendly": "Error: Command cannot be empty",
                "detailed": "Command cannot be empty",
            }

        try:
            timeout = int(timeout)
        except (ValueError, TypeError):
            timeout = DEFAULT_TIMEOUT

        output = execute_shell(command, timeout, cwd)

        return {
            "tool": "shell_exec",
            "friendly": f"Executed: {command}",
            "detailed": output,
        }

    # Format function for shell_exec (shows command during approval)
    def format_shell_exec(args):
        """Format arguments for shell_exec"""
        command = args.get("command", "")
        timeout = args.get("timeout", DEFAULT_TIMEOUT)
        cwd = args.get("cwd", "current dir")
        return f"Command: {command}\nTimeout: {timeout}s\nWorking dir: {cwd}"

    # Register the /shell command
    ctx.register_command("/shell", handle_shell_command, description="Execute shell commands")

    # Register the shell_exec tool (NOT auto-approved - requires user confirmation)
    ctx.register_tool(
        name="shell_exec",
        fn=shell_exec,
        description="Execute shell commands (e.g., pwd, ls, cp, etc.)",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                    "default": 30
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (default: current directory)"
                }
            },
            "required": ["command"]
        },
        auto_approved=False,
        format_arguments=format_shell_exec
    )

    print("  - /shell command")
    print("  - shell_exec tool")
