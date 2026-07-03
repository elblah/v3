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
        if not args:
            # Show status
            dm_status = "ENABLED" if Config.detail_mode() else "DISABLED"
            dm_color = "green" if Config.detail_mode() else "yellow"
            LogUtils.print(f"Detail Mode: {dm_status}", color=dm_color, bold=True)

            tty_status = "ON" if Config.detail_tty() else "OFF"
            tty_color = "green" if Config.detail_tty() else "yellow"
            LogUtils.print(f"TTY Passthrough: {tty_status}", color=tty_color, bold=True)

            if Config.detail_mode():
                LogUtils.success("All tool parameters and results will be shown")
            else:
                LogUtils.warn("Only important tool information will be shown")

            if Config.detail_tty():
                LogUtils.success("Command output also shown live in terminal via /dev/tty")

            LogUtils.dim("Usage: /detail [on|off|toggle|tty on|off|help]")
            return CommandResult(should_quit=False, run_api_call=False)

        action = args[0].lower()

        # Handle tty subcommand
        if action == "tty":
            if len(args) < 2:
                tty_status = "ON" if Config.detail_tty() else "OFF"
                LogUtils.print(f"TTY Passthrough: {tty_status}", color="green" if Config.detail_tty() else "yellow", bold=True)
                if Config.detail_tty():
                    LogUtils.success("Command output is shown live in terminal")
                LogUtils.dim("Usage: /detail tty on|off")
                return CommandResult(should_quit=False, run_api_call=False)

            tty_action = args[1].lower()
            if tty_action in ("on", "1", "enable", "true"):
                if Config.detail_tty():
                    LogUtils.warn("[*] TTY passthrough is already ON")
                else:
                    Config.set_detail_tty(True)
                    LogUtils.success("[*] TTY passthrough ENABLED")
                    LogUtils.info("Command output will also be shown live in terminal")
            elif tty_action in ("off", "0", "disable", "false"):
                if Config.detail_tty():
                    Config.set_detail_tty(False)
                    LogUtils.warn("[*] TTY passthrough DISABLED")
                else:
                    LogUtils.warn("[*] TTY passthrough is already OFF")
            else:
                LogUtils.error("Invalid tty argument. Use: /detail tty on|off")
            return CommandResult(should_quit=False, run_api_call=False)

        # Handle tty help explicit
        if action == "help":
            LogUtils.print("Detail Mode Controls:", color="cyan", bold=True)
            LogUtils.dim("  /detail           - Show current detail and TTY status")
            LogUtils.dim("  /detail on|off    - Toggle detailed tool output mode")
            LogUtils.dim("  /detail toggle    - Toggle between on/off")
            LogUtils.dim("  /detail tty on    - Enable live terminal output (/dev/tty)")
            LogUtils.dim("  /detail tty off   - Disable live terminal output")
            LogUtils.dim("  /detail help      - Show this help")
            LogUtils.dim("")
            LogUtils.info("TTY mode: when ON, command output goes to both the AI and")
            LogUtils.info("your terminal in real-time (via tee /dev/tty). Useful for")
            LogUtils.info("long-running commands like builds where you want to see")
            LogUtils.info("progress without waiting for the AI's turn to finish.")
            return CommandResult(should_quit=False, run_api_call=False)

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
            LogUtils.error("Invalid argument. Use: /detail [on|off|toggle|tty on|off|help]")
            LogUtils.dim("  /detail - Show current status")
            LogUtils.dim("  /detail on - Enable detailed output")
            LogUtils.dim("  /detail off - Disable detailed output (show friendly messages)")
            LogUtils.dim("  /detail toggle - Toggle between on/off")
            LogUtils.dim("  /detail tty on|off - Toggle TTY passthrough (live terminal output)")

        return CommandResult(should_quit=False, run_api_call=False)
