"""
YOLO command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class YoloCommand(BaseCommand):
    """Show or configure YOLO mode (auto-approve tool actions)"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "yolo"
        self._description = "Show or configure YOLO mode (auto-approve tool actions)"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["y"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute YOLO command"""
        if args is None:
            args = []

        status = "ENABLED" if Config.yolo_mode() else "DISABLED"
        status_color = (
            Config.colors["green"] if Config.yolo_mode() else Config.colors["red"]
        )

        if not args:
            # Show status
            LogUtils.print(
                f"{Config.colors['bold']}YOLO Mode Status:{Config.colors['reset']} {status_color}{status}{Config.colors['reset']}"
            )

            if Config.yolo_mode():
                LogUtils.print(
                    f"{Config.colors['green']}All tool actions will be auto-approved{Config.colors['reset']}"
                )
                LogUtils.print(
                    f"{Config.colors['yellow']}{Config.colors['bold']}[!] This includes run_shell_command - use with caution!{Config.colors['reset']}"
                )
            else:
                LogUtils.print(
                    f"{Config.colors['red']}Tool actions require explicit approval{Config.colors['reset']}"
                )
                LogUtils.print(
                    f"{Config.colors['green']}Safe mode - you will be prompted before each action{Config.colors['reset']}"
                )

            LogUtils.print(
                f"{Config.colors['dim']}To enable YOLO: /yolo on or export YOLO_MODE=1{Config.colors['reset']}"
            )
            LogUtils.print(
                f"{Config.colors['dim']}To disable YOLO: /yolo off or unset YOLO_MODE{Config.colors['reset']}"
            )

            return CommandResult(should_quit=False, run_api_call=False)

        action = args[0].lower()
        if action in ["on", "1"]:
            if Config.yolo_mode():
                LogUtils.print(
                    f"{Config.colors['yellow']}YOLO mode is already enabled{Config.colors['reset']}"
                )
            else:
                Config.set_yolo_mode(True)
                LogUtils.print(
                    f"{Config.colors['green']}YOLO mode ENABLED - All tool actions will auto-approve{Config.colors['reset']}"
                )
                LogUtils.print(
                    f"{Config.colors['yellow']}{Config.colors['bold']}[!] This includes potentially dangerous shell commands{Config.colors['reset']}"
                )
        elif action in ["off", "0"]:
            if Config.yolo_mode():
                Config.set_yolo_mode(False)
                LogUtils.print(
                    f"{Config.colors['red']}YOLO mode DISABLED - Tool actions require approval{Config.colors['reset']}"
                )
                LogUtils.print(
                    f"{Config.colors['green']}Safe mode restored - you will be prompted for each action{Config.colors['reset']}"
                )
            else:
                LogUtils.print(
                    f"{Config.colors['red']}YOLO mode is already disabled{Config.colors['reset']}"
                )
        else:
            LogUtils.print(
                f"{Config.colors['red']}Invalid argument. Use: /yolo [on|off]{Config.colors['reset']}"
            )

        return CommandResult(should_quit=False, run_api_call=False)
