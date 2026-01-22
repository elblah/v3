"""
Detail command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class DetailCommand(BaseCommand):
    """Toggle detailed tool output on/off"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "detail"
        self._description = "Toggle detailed tool output on/off"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["d"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute detail command"""
        status = "ENABLED" if Config.detail_mode() else "DISABLED"
        status_color = "green" if Config.detail_mode() else "yellow"

        if not args:
            # Show status
            LogUtils.print(f"Detail Mode Status: {status}", color=status_color, bold=True)

            if Config.detail_mode():
                LogUtils.success("All tool parameters and results will be shown")
                LogUtils.info("Use Ctrl+Z or /detail off to switch to simple mode")
            else:
                LogUtils.warn("Only important tool information will be shown")
                LogUtils.info("Use Ctrl+Z or /detail on to switch to detailed mode")

            LogUtils.dim("Quick toggle: Ctrl+Z | Command: /detail [on|off]")
            return CommandResult(should_quit=False, run_api_call=False)

        action = args[0].lower()
        if action in ("on", "1", "enable", "true"):
            if Config.detail_mode():
                LogUtils.warn("[*] Detail mode is already enabled")
            else:
                Config.set_detail_mode(True)
                LogUtils.success("[*] Detail mode ENABLED")
                LogUtils.info("All tool parameters and results will now be shown")
        elif action in ("off", "0", "disable", "false"):
            if Config.detail_mode():
                Config.set_detail_mode(False)
                LogUtils.warn("[*] Detail mode DISABLED")
                LogUtils.info("Only important tool information will be shown")
            else:
                LogUtils.warn("[*] Detail mode is already disabled")
        elif action == "toggle":
            Config.set_detail_mode(not Config.detail_mode())

            if Config.detail_mode():
                LogUtils.success("[*] Detail mode ENABLED")
                LogUtils.info("All tool parameters and results will now be shown")
            else:
                LogUtils.warn("[*] Detail mode DISABLED")
                LogUtils.info("Only important tool information will be shown")
        else:
            LogUtils.error("Invalid argument. Use: /detail [on|off|toggle]")
            LogUtils.dim("  /detail - Show current status")
            LogUtils.dim("  /detail on - Enable detailed output")
            LogUtils.dim("  /detail off - Disable detailed output (show friendly messages)")
            LogUtils.dim("  /detail toggle - Toggle between on/off")
            LogUtils.dim("  Ctrl+Z - Quick toggle")

        return CommandResult(should_quit=False, run_api_call=False)
