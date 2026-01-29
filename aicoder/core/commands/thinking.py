"""
Thinking command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class ThinkingCommand(BaseCommand):
    """Control thinking mode for models that support it"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "thinking"
        self._description = "Control thinking mode (default/on/off)"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute thinking command"""
        current_mode = Config.thinking()

        if not args:
            # Show status
            if current_mode == "default":
                status = "default (not controlling behavior, using API defaults)"
                status_color = "yellow"
            elif current_mode == "on":
                status = "on (explicitly enabled)"
                status_color = "green"
            else:
                status = "off (explicitly disabled)"
                status_color = "brightRed"

            LogUtils.print(f"Thinking: {status}", color=status_color, bold=True)

            if current_mode == "default":
                LogUtils.info("Model will use its default thinking behavior")
            elif current_mode == "on":
                LogUtils.info("Sending extra_body: {\"thinking\": {\"type\": \"enabled\"}}")
            else:
                LogUtils.info("Sending extra_body: {\"thinking\": {\"type\": \"disabled\"}}")

            LogUtils.dim("Use: /thinking [default|on|off]")
            return CommandResult(should_quit=False, run_api_call=False)

        action = args[0].lower()

        action = args[0].lower()

        if action == "default":
            if current_mode == "default":
                LogUtils.warn("[*] Thinking is already set to default")
            else:
                Config.set_thinking("default")
                LogUtils.success("[*] Thinking set to default")
                LogUtils.info("Model will use its default thinking behavior")
        elif action in ("on", "1", "enable", "true"):
            if current_mode == "on":
                LogUtils.warn("[*] Thinking is already enabled")
            else:
                Config.set_thinking("on")
                LogUtils.success("[*] Thinking ENABLED")
                LogUtils.info("Sending thinking enabled in API requests")
        elif action in ("off", "0", "disable", "false"):
            if current_mode == "off":
                LogUtils.warn("[*] Thinking is already disabled")
            else:
                Config.set_thinking("off")
                LogUtils.warn("[*] Thinking DISABLED")
                LogUtils.info("Sending thinking disabled in API requests")
        elif action == "toggle":
            # Toggle between on and off
            if current_mode == "on":
                Config.set_thinking("off")
                LogUtils.warn("[*] Thinking DISABLED")
                LogUtils.info("Sending thinking disabled in API requests")
            elif current_mode == "off":
                Config.set_thinking("on")
                LogUtils.success("[*] Thinking ENABLED")
                LogUtils.info("Sending thinking enabled in API requests")
            else:
                # If default, turn it on
                Config.set_thinking("on")
                LogUtils.success("[*] Thinking ENABLED")
                LogUtils.info("Sending thinking enabled in API requests")
        else:
            LogUtils.error("Invalid argument. Use: /thinking [default|on|off]")
            LogUtils.dim("  /thinking - Show current status")
            LogUtils.dim("  /thinking default - Use API defaults (don't send extra_body)")
            LogUtils.dim("  /thinking on - Explicitly enable thinking")
            LogUtils.dim("  /thinking off - Explicitly disable thinking")
            LogUtils.dim("  /thinking toggle - Toggle between on/off")

        return CommandResult(should_quit=False, run_api_call=False)
