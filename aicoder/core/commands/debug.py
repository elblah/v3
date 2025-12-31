"""
Debug command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils, LogOptions


class DebugCommand(BaseCommand):
    """Toggle debug mode or trigger breakpoint"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "debug"
        self._description = "Toggle debug mode or trigger breakpoint"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["dbg"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute debug command"""
        if args is None:
            args = []

        # Show status if no args
        if not args:
            return self._show_status()

        action = args[0].lower()

        # Handle breakpoint/break
        if action in ["breakpoint", "bp", "break", "b"]:
            return self._trigger_breakpoint()

        # Handle on/off/toggle
        if action in ["on", "1", "enable", "true"]:
            return self._enable_debug()
        elif action in ["off", "0", "disable", "false"]:
            return self._disable_debug()
        elif action in ["toggle", "t"]:
            if Config.debug():
                return self._disable_debug()
            else:
                return self._enable_debug()
        else:
            LogUtils.error(f"Invalid argument: {action}")
            LogUtils.print("Usage: /debug [on|off|toggle|breakpoint]")
            return CommandResult(should_quit=False, run_api_call=False)

    def _show_status(self) -> CommandResult:
        """Show current debug status"""
        status = "ENABLED" if Config.debug() else "DISABLED"
        status_color = (
            Config.colors["green"] if Config.debug() else Config.colors["yellow"]
        )

        LogUtils.print(
            f"Debug Mode Status: {status}",
            LogOptions(color=status_color, bold=True),
        )

        if Config.debug():
            LogUtils.success("Debug logging is active")
            LogUtils.print(
                "  - Detailed output will be shown for API calls",
                LogOptions(color=Config.colors["cyan"]),
            )
        else:
            LogUtils.warn("Debug logging is disabled")
            LogUtils.print(
                "  - Use /debug on to enable",
                LogOptions(color=Config.colors["cyan"]),
            )

        LogUtils.print(
            "\nQuick actions:",
            LogOptions(color=Config.colors["dim"]),
        )
        LogUtils.print(
            "  /debug on|off|toggle - Manage debug mode",
            LogOptions(color=Config.colors["dim"]),
        )
        LogUtils.print(
            "  /debug breakpoint|bp|break - Trigger Python breakpoint() for debugging",
            LogOptions(color=Config.colors["dim"]),
        )

        return CommandResult(should_quit=False, run_api_call=False)

    def _enable_debug(self) -> CommandResult:
        """Enable debug mode"""
        if Config.debug():
            LogUtils.warn("[*] Debug mode is already enabled")
        else:
            Config.set_debug(True)
            LogUtils.success("[*] Debug mode ENABLED")
            LogUtils.print(
                "Detailed output will now be shown for API calls",
                LogOptions(color=Config.colors["cyan"]),
            )
        return CommandResult(should_quit=False, run_api_call=False)

    def _disable_debug(self) -> CommandResult:
        """Disable debug mode"""
        if Config.debug():
            Config.set_debug(False)
            LogUtils.warn("[*] Debug mode DISABLED")
            LogUtils.print(
                "Only essential output will be shown",
                LogOptions(color=Config.colors["cyan"]),
            )
        else:
            LogUtils.warn("[*] Debug mode is already disabled")
        return CommandResult(should_quit=False, run_api_call=False)

    def _trigger_breakpoint(self) -> CommandResult:
        """Trigger a Python breakpoint for debugging"""
        LogUtils.print(
            "\n[*] Triggering Python breakpoint()...",
            LogOptions(color=Config.colors["yellow"], bold=True),
        )
        LogUtils.print(
            "    Use 'c' to continue, 'q' to quit, or explore variables",
            LogOptions(color=Config.colors["cyan"]),
        )
        LogUtils.print(
            "    Type 'help' for debugger commands\n",
            LogOptions(color=Config.colors["dim"]),
        )

        # Trigger the actual breakpoint
        breakpoint()

        LogUtils.print(
            "\n[*] Breakpoint session ended",
            LogOptions(color=Config.colors["green"]),
        )
        return CommandResult(should_quit=False, run_api_call=False)
