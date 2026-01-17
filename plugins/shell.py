"""
Shell Plugin - Execute shell commands

Features:
- Direct command execution via /shell command
- Useful for checking current directory (pwd), file operations, etc.

Commands:
- /shell <command> - Execute a shell command directly
"""

import subprocess
import os
from typing import Dict, Any

from aicoder.core.config import Config


def create_plugin(ctx):
    """Shell command execution plugin"""

    DEFAULT_TIMEOUT = 600  # 10 minutes - generous timeout with safety net
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

Note: Commands have a 10-minute timeout (use Ctrl+C to cancel earlier).
"""

        command = args_str.strip()
        output = execute_shell(command, DEFAULT_TIMEOUT)
        return output

    # Register the /shell command
    ctx.register_command("/shell", handle_shell_command, description="Execute shell commands")

    if Config.debug():
        print("  - /shell command")
