"""
Detail command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils, LogOptions


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
        status_color = (
            Config.colors["green"] if Config.detail_mode() else Config.colors["yellow"]
        )

        if not args:
            # Show status
            LogUtils.print(
                f"Detail Mode Status: {status}",
                LogOptions(color=status_color, bold=True),
            )

            if Config.detail_mode():
                LogUtils.success("All tool parameters and results will be shown")
                LogUtils.print(
                    "Use Ctrl+Z or /detail off to switch to simple mode",
                    LogOptions(color=Config.colors["cyan"]),
                )
            else:
                LogUtils.warn("Only important tool information will be shown")
                LogUtils.print(
                    "Use Ctrl+Z or /detail on to switch to detailed mode",
                    LogOptions(color=Config.colors["cyan"]),
                )

            LogUtils.print(
                "Quick toggle: Ctrl+Z | Command: /detail [on|off]",
                LogOptions(color=Config.colors["dim"]),
            )
            return CommandResult(should_quit=False, run_api_call=False)

        action = args[0].lower()
        if action in ("on", "1", "enable", "true"):
            if Config.detail_mode():
                LogUtils.warn("[*] Detail mode is already enabled")
            else:
                Config.set_detail_mode(True)
                LogUtils.success("[*] Detail mode ENABLED")
                LogUtils.print(
                    "All tool parameters and results will now be shown",
                    LogOptions(color=Config.colors["cyan"]),
                )
        elif action in ("off", "0", "disable", "false"):
            if Config.detail_mode():
                Config.set_detail_mode(False)
                LogUtils.warn("[*] Detail mode DISABLED")
                LogUtils.print(
                    "Only important tool information will be shown",
                    LogOptions(color=Config.colors["cyan"]),
                )
            else:
                LogUtils.warn("[*] Detail mode is already disabled")
        elif action == "toggle":
            Config.set_detail_mode(not Config.detail_mode())
            new_status = "ENABLED" if Config.detail_mode() else "DISABLED"

            if Config.detail_mode():
                LogUtils.success(f"[*] Detail mode ENABLED")
                LogUtils.print(
                    "All tool parameters and results will now be shown",
                    LogOptions(color=Config.colors["cyan"]),
                )
            else:
                LogUtils.warn(f"[*] Detail mode DISABLED")
                LogUtils.print(
                    "Only important tool information will be shown",
                    LogOptions(color=Config.colors["cyan"]),
                )
        else:
            LogUtils.error("Invalid argument. Use: /detail [on|off|toggle]")
            LogUtils.print(
                "  /detail - Show current status",
                LogOptions(color=Config.colors["dim"]),
            )
            LogUtils.print(
                "  /detail on - Enable detailed output",
                LogOptions(color=Config.colors["dim"]),
            )
            LogUtils.print(
                "  /detail off - Disable detailed output (show friendly messages)",
                LogOptions(color=Config.colors["dim"]),
            )
            LogUtils.print(
                "  /detail toggle - Toggle between on/off",
                LogOptions(color=Config.colors["dim"]),
            )
            LogUtils.print(
                "  Ctrl+Z - Quick toggle", LogOptions(color=Config.colors["dim"])
            )

        return CommandResult(should_quit=False, run_api_call=False)
