"""
Ruff Plugin - Automatic Python code quality checks

Features:
- Automatic ruff check on .py file writes/edits
- User message generation when serious issues found
- Configurable via /ruff command
- Graceful fallback when ruff not installed
- Default: serious-only mode (ignores minor linting issues)

Commands:
- /ruff - Show status
- /ruff on/off - Enable/disable
- /ruff check-serious on/off - Toggle serious-only mode
"""

import os


def create_plugin(ctx):
    """Automatic Python code quality checks with ruff"""

    # Plugin state in closure
    state = {
        "enabled": True,
        "serious_only": True,  # Default: only check serious issues
        "check_args": "",
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
            result = ctx.run_shell("which ruff", timeout=5)
            if "not found" in result.lower() or result.strip() == "":
                return None  # ruff not installed, silently skip
        except:
            return None

        args = get_effective_args()
        cmd = f'ruff check {args} "{filepath}"'

        result = ctx.run_shell(cmd, timeout=10)

        if result and ("error" in result.lower() or "found" in result.lower()):
            return f"Ruff issues in {filepath}:\n{result}"
        return None

    def after_file_write(path: str, content: str) -> None:
        """Hook: After file write - run ruff check"""
        issues = run_ruff_check(path)
        if issues:
            ctx.log(issues)
            # Add message for AI to fix (this will be AFTER tool result)
            ctx.add_user_message(f"\n{issues}\n")

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
    ctx.register_command("/ruff", handle_ruff_command, description="Ruff code quality checks")

    print("  - after_file_write hook")
    print("  - /ruff command")
