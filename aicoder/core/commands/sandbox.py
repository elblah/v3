"""
Sandbox command implementation
"""

import os
from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class SandboxCommand(BaseCommand):
    """Show or configure filesystem sandbox status"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "sandbox-fs"
        self._description = "Show or configure filesystem sandbox status"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["sfs"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute sandbox command"""
        if args is None:
            args = []

        status = "DISABLED" if Config.sandbox_disabled() else "ENABLED"
        status_color = (
            Config.colors["red"]
            if Config.sandbox_disabled()
            else Config.colors["green"]
        )

        if not args:
            # Show status
            LogUtils.print(
                f"sandbox-fs Status: {status}", color=status_color, bold=True
            )
            LogUtils.print(
                f"Current directory: {os.getcwd()}", color=Config.colors["cyan"]
            )

            if Config.sandbox_disabled():
                LogUtils.warn("Sandbox-fs is DISABLED")
                LogUtils.warn("File operations can access any path on the system")
            else:
                LogUtils.success("Sandbox-fs is ENABLED")
                LogUtils.success(
                    "File operations for internal tools are limited to current directory and subdirectories"
                )

            LogUtils.print(
                "Use /sandbox-fs on|off to toggle at runtime",
                color=Config.colors["dim"],
            )

            return CommandResult(should_quit=False, run_api_call=False)

        action = args[0].lower()
        if action in ["on", "1"]:
            if Config.sandbox_disabled():
                Config.set_sandbox_disabled(False)
                LogUtils.success("Sandbox-fs is now enabled")
            else:
                LogUtils.warn("Sandbox-fs is already enabled")
        elif action in ["off", "0"]:
            if Config.sandbox_disabled():
                LogUtils.error("Sandbox-fs is already disabled")
            else:
                Config.set_sandbox_disabled(True)
                LogUtils.success("Sandbox-fs is now disabled")
        else:
            LogUtils.error("Invalid argument. Use: /sandbox-fs [on|off]")

        return CommandResult(should_quit=False, run_api_call=False)
