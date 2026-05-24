"""
Shell command utilities that work across environments
Stateless module functions - no classes needed
"""

import subprocess
from typing import Dict, Any


class ShellResult:
    """Result of shell command execution - simple class instead of dataclass"""

    __slots__ = ('success', 'exit_code', 'stdout', 'stderr')

    def __init__(self, success: bool, exit_code: int, stdout: str, stderr: str):
        self.success = success
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


def execute_command_sync(command: str) -> ShellResult:
    """Execute shell command synchronously"""
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )

        return ShellResult(
            success=result.returncode == 0,
            exit_code=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )
    except subprocess.TimeoutExpired:
        return ShellResult(
            success=False,
            exit_code=124,  # timeout exit code
            stdout="",
            stderr="Command timed out",
        )
    except Exception as error:
        return ShellResult(success=False, exit_code=-1, stdout="", stderr=str(error))


def execute_command_with_timeout(command: str, timeout_seconds: int) -> ShellResult:
    """Execute command with timeout"""
    timeout_command = (
        f'timeout -k 5 {timeout_seconds}s bash -c "{command.replace('"', '\\"')}"'
    )
    return execute_command_sync(timeout_command)
