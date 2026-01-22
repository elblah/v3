"""
Debug command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


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
        status_color = "green" if Config.debug() else "yellow"

        LogUtils.print(f"Debug Mode Status: {status}", color=status_color, bold=True)

        if Config.debug():
            LogUtils.success("Debug logging is active")
            LogUtils.info("Detailed output will be shown for API calls")
        else:
            LogUtils.warn("Debug logging is disabled")
            LogUtils.info("Use /debug on to enable")

        LogUtils.dim("\nQuick actions:")
        LogUtils.dim("  /debug on|off|toggle - Manage debug mode")
        LogUtils.dim("  /debug breakpoint|bp|break - Trigger Python breakpoint() for debugging")

        return CommandResult(should_quit=False, run_api_call=False)

    def _enable_debug(self) -> CommandResult:
        """Enable debug mode"""
        if Config.debug():
            LogUtils.warn("[*] Debug mode is already enabled")
        else:
            Config.set_debug(True)
            LogUtils.success("[*] Debug mode ENABLED")
            LogUtils.info("Detailed output will now be shown for API calls")
        return CommandResult(should_quit=False, run_api_call=False)

    def _disable_debug(self) -> CommandResult:
        """Disable debug mode"""
        if Config.debug():
            Config.set_debug(False)
            LogUtils.warn("[*] Debug mode DISABLED")
            LogUtils.info("Only essential output will be shown")
        else:
            LogUtils.warn("[*] Debug mode is already disabled")
        return CommandResult(should_quit=False, run_api_call=False)

    def _trigger_breakpoint(self) -> CommandResult:
        """Trigger a Python breakpoint for debugging"""
        LogUtils.warn("\n[*] Triggering Python breakpoint()...")
        LogUtils.info("    Use 'c' to continue, 'q' to quit, or explore variables")
        LogUtils.dim("    Type 'help' for debugger commands\n")

        # Trigger the actual breakpoint
        breakpoint()

        LogUtils.success("\n[*] Breakpoint session ended")
        return CommandResult(should_quit=False, run_api_call=False)
