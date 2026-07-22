"""
Run shell command tool

"""

import subprocess
import signal
import os
import time
from typing import Dict, Any, Optional
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# Configuration
DEFAULT_TIMEOUT = Config.default_shell_timeout()


# Global reference to active subprocess for Ctrl+C cleanup
_active_proc: Optional[subprocess.Popen] = None
_tty_path: Optional[str] = None


def get_tty_path() -> str:
    """Detect and cache the terminal device path.
    
    Tries os.ttyname() on stdin/stdout/stderr, falls back to /dev/tty.
    Returns empty string if no TTY is available (e.g. Android/Termux where
    /dev/tty doesn't exist but ttyname still works on the pty fd).
    """
    global _tty_path
    if _tty_path is not None:
        return _tty_path
    
    for fd in [0, 1, 2]:
        try:
            if os.isatty(fd):
                _tty_path = os.ttyname(fd)
                return _tty_path
        except OSError:
            pass
    
    if os.path.exists("/dev/tty"):
        _tty_path = "/dev/tty"
        return _tty_path
    
    _tty_path = ""
    return _tty_path


def _get_cleared_env() -> Optional[Dict[str, str]]:
    """Get environment with vars from AICODER_SHELL_CLEAR_VARS removed."""
    clear_vars = os.environ.get("AICODER_SHELL_CLEAR_VARS")
    if not clear_vars:
        return None
    
    vars_to_clear = [v.strip() for v in clear_vars.split(",") if v.strip()]
    if not vars_to_clear:
        return None
    
    return {k: v for k, v in os.environ.items() if k not in vars_to_clear}


def _kill_process_group(proc: subprocess.Popen) -> None:
    """Kill entire process group"""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass  # Process already dead or can't access


def kill_active_process() -> None:
    """Kill active subprocess if exists (called before showing prompt)"""
    global _active_proc
    if _active_proc is not None:
        _kill_process_group(_active_proc)
        _active_proc = None


def _wrap_with_tee(command: str) -> Optional[str]:
    """Wrap command so output goes to both TTY and stdout/stderr pipes.
    
    Uses tee to duplicate output to the user's terminal in real-time
    while still capturing it for the AI. Preserves exit codes via PIPESTATUS.
    Returns None if no TTY is available.
    """
    tty = get_tty_path()
    if not tty:
        return None
    return f"({command}) 2>&1 | tee {tty} 2>/dev/null; exit ${{PIPESTATUS[0]}}"


def execute_with_process_group(command: str, timeout: int, cwd: Optional[str] = None, live_output: bool = False) -> subprocess.CompletedProcess:
    """Execute command with proper process group termination"""
    global _active_proc

    # Get env with cleared vars (or None to inherit parent env)
    clean_env = _get_cleared_env()

    # Wrap command with tee when detail TTY passthrough is enabled OR per-call live_output flag
    if Config.detail_tty() or live_output:
        wrapped = _wrap_with_tee(command)
        if wrapped:
            command = wrapped

    # Create process group for the entire process tree
    proc = subprocess.Popen(
        ["bash", "-c", command],
        shell=False,
        preexec_fn=os.setsid,  # Create new process group
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=clean_env,
    )

    _active_proc = proc

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
        _kill_process_group(proc)
        time.sleep(2)  # Give it a moment to cleanup gracefully
        _kill_process_group(proc)  # Force kill if still running

        # Get remaining output
        stdout, stderr = proc.communicate()

        return subprocess.CompletedProcess(
            args=command,
            returncode=-1,  # Custom code for timeout
            stdout=stdout,
            stderr=stderr
        )

    finally:
        # Always clean up process group to ensure spawned children are killed
        if _active_proc is not None:
            if Config.debug():
                LogUtils.debug(f"[*] Killing active subprocess (PID: {_active_proc.pid})")
            _kill_process_group(_active_proc)
            # Reap the process to clean up zombies
            try:
                _active_proc.communicate(timeout=1)
            except Exception:
                pass
            _active_proc = None


def execute(args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute shell command with timeout"""
    command = args.get("command")
    try:
        timeout = int(args.get("timeout", DEFAULT_TIMEOUT))
    except ValueError:
        raise Exception("timeout must be an integer, got: " + str(args.get("timeout")))
    cwd = args.get("cwd")
    live_output = args.get("live_output", False)

    if not command:
        raise Exception("Command is required")

    # Prepend wrapper script if configured (e.g. AICODER_SHELL_PREPEND_CMD="rtk")
    prepend = Config.shell_prepend_cmd()
    if prepend:
        command = f"{prepend} {command}"
        if Config.debug():
            LogUtils.debug(f"[prepend-cmd] wrapped: {command!r}")

    try:
        # Execute command with proper process group termination
        result = execute_with_process_group(command, timeout, cwd, live_output=live_output)

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

        # Build detailed message with explicit timeout information for AI
        if result.returncode == -1:
            # Make timeout VERY clear to AI with actionable suggestion
            detailed = f"COMMAND TIMED OUT after {timeout} seconds\n\n"
            detailed += f"Command: {command}\n"
            detailed += f"Exit code: {result.returncode} (timeout indicator)\n"
            detailed += f"Working directory: {cwd or '.'}\n\n"
            detailed += f"Output captured before timeout:\n{output if output else '(no output captured before timeout)'}\n\n"
            detailed += f"GUIDANCE: If this task needs to complete, use a timeout appropriate for your environment:\n"
            detailed += f"  - Quick commands (ls, cat, git status): 10-30s\n"
            detailed += f"  - Package installs (npm, pip, cargo): 300-600s\n"
            detailed += f"  - Compilation (go build, make, cargo build): 600-3600s on slow hardware\n"
            detailed += f"If the timeout was intentional (e.g., testing if a server starts correctly), no action needed."
        else:
            detailed = f"Command: {command}\nExit code: {result.returncode}\nTimeout: {timeout}s\nWorking directory: {cwd or '.'}\n\nOutput:\n{output}"

        return {
            "tool": "run_shell_command",
            "friendly": friendly,
            "detailed": detailed
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
    "description": "Execute bash command with timeout",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "bash command to execute"},
            "timeout": {
                "type": "integer",
                "description": f"Timeout in seconds (default: {DEFAULT_TIMEOUT}). IMPORTANT: For slow environments or compilation tasks (go build, cargo build, make, npm install, etc.), use much larger timeouts like 3600 (1 hour) to avoid wasting time on repeated timeout failures.",
                "default": DEFAULT_TIMEOUT,
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (optional)",
                "default": None,
            },
            "live_output": {
                "type": "boolean",
                "description": "Show output live in user's terminal (default: false). Set true for long-running commands where user wants to see progress.",
                "default": False,
            },
        },
        "required": ["command"],
    },
}


def format_arguments(args):
    """Format arguments for display"""
    command = args.get("command")
    try:
        timeout = int(args.get("timeout", DEFAULT_TIMEOUT))
    except ValueError:
        raise Exception("timeout must be an integer, got: " + str(args.get("timeout")))

    lines = []
    if command:
        lines.append(f"Command: {command}")

    if timeout != DEFAULT_TIMEOUT:
        lines.append(f"Timeout: {timeout}s")

    if args.get("live_output"):
        lines.append("Live output: ON (shown in terminal)")

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
