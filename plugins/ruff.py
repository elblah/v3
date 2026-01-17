"""
Ruff Plugin - Automatic Python code quality checks

Features:
- Automatic ruff check on .py file writes/edits
- User message generation when serious issues found
- Configurable via /ruff command
- Graceful fallback when ruff not installed
- Default: serious-only mode (ignores minor linting issues)
- Messages added AFTER tool results to avoid breaking conversation flow

Commands:
- /ruff - Show status
- /ruff on/off - Enable/disable
- /ruff check-serious on/off - Toggle serious-only mode
"""

import os
import subprocess

from aicoder.core.config import Config


def create_plugin(ctx):
    """Automatic Python code quality checks with ruff"""

    # Plugin state in closure
    state = {
        "enabled": True,
        "serious_only": True,  # Default: only check serious issues
        "check_args": "",
        "pending_files": [],  # Files to check after tool results
    }

    def get_effective_args() -> str:
        """Get effective ruff arguments based on mode"""
        if state["serious_only"]:
            # Only check errors (E) and serious issues, ignore minor stuff
            return "--select E,F --ignore E501,F841,E712,F401,E722,F541"
        return state["check_args"]

    def run_ruff_check(filepath: str) -> str:
        """Run ruff check on a file"""
        if not state["enabled"]:
            return None

        if not filepath.endswith(".py"):
            return None

        # Check if ruff exists
        try:
            result = subprocess.run(
                ["which", "ruff"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if "not found" in result.stdout.lower() or result.stdout.strip() == "":
                return None  # ruff not installed, silently skip
        except:
            return None

        args = get_effective_args()
        cmd = f'ruff check {args} "{filepath}"'

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.stdout and ("error" in result.stdout.lower() or "found" in result.stdout.lower()):
            return f"Ruff issues in {filepath}:\n{result.stdout}"
        return None

    def after_file_write(path: str, content: str) -> None:
        """Hook: After file write - queue file for ruff check"""
        # Just queue the file, don't check yet
        # This ensures tool results are added before any plugin messages
        if path.endswith(".py"):
            state["pending_files"].append(path)

    def after_tool_results(tool_results) -> None:
        """Hook: After tool results added - check queued files"""
        # Check all queued files
        while state["pending_files"]:
            filepath = state["pending_files"].pop(0)
            issues = run_ruff_check(filepath)
            if issues:
                print(f"[plugin] {issues}")
                # Add message for AI to fix (this will be AFTER tool result)
                ctx.app.message_history.add_user_message(f"\n{issues}\n")

    def handle_ruff_command(args_str: str) -> str:
        """Handle /ruff command"""
        if not args_str:
            # Show status
            enabled_str = "enabled" if state["enabled"] else "disabled"
            serious_str = "enabled" if state["serious_only"] else "disabled"
            return f"""Ruff Plugin Status:

- Checking: {enabled_str}
- Serious-only mode: {serious_str}

Commands:
- /ruff on/off - Enable/disable checking
- /ruff check-serious on/off - Toggle serious-only mode
"""

        parts = args_str.strip().split()
        if not parts:
            return "Usage: /ruff [on|off|check-serious [on|off]]"

        if parts[0] == "on":
            state["enabled"] = True
            return "Ruff checking enabled"
        elif parts[0] == "off":
            state["enabled"] = False
            return "Ruff checking disabled"
        elif parts[0] == "check-serious":
            if len(parts) >= 2 and parts[1] in ("on", "off"):
                state["serious_only"] = parts[1] == "on"
                mode = "serious-only" if state["serious_only"] else "full"
                return f"Ruff set to {mode} mode"
            else:
                mode = "serious-only" if state["serious_only"] else "full"
                return f"Ruff mode: {mode} (use on/off to change)"

        return "Unknown command. Use: /ruff [on|off|check-serious [on|off]]"

    # Register hooks and command
    ctx.register_hook("after_file_write", after_file_write)
    ctx.register_hook("after_tool_results", after_tool_results)
    ctx.register_command("/ruff", handle_ruff_command, description="Ruff code quality checks")

    if Config.debug():
        print("  - after_file_write hook")
        print("  - after_tool_results hook")
        print("  - /ruff command")
