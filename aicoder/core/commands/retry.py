"""
Retry command implementation - minimalist approach
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class RetryCommand(BaseCommand):
    """Retry the last message or configure retry limit"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "retry"
        self._description = "Retry the last message or configure retry limit"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["r"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute retry command"""
        if args is None:
            args = []

        # Handle /retry help
        if len(args) >= 1 and args[0].lower() == "help":
            self.show_help()
            return CommandResult(should_quit=False, run_api_call=False)

        # Handle /retry limit [n]
        if len(args) >= 1 and args[0].lower() == "limit":
            if len(args) >= 2:
                self.handle_limit(args[1])
            else:
                self.show_current_limit()
            return CommandResult(should_quit=False, run_api_call=False)

        # Default: retry last request
        messages = self.context.message_history.get_messages()
        has_user_message = any(msg.get("role") == "user" for msg in messages)

        if not has_user_message:
            LogUtils.error("[*] Cannot retry: No user messages found")
            return CommandResult(should_quit=False, run_api_call=False)

        LogUtils.print("[*] Retrying last request...")
        return CommandResult(should_quit=False, run_api_call=True)

    def handle_limit(self, value: str) -> None:
        """Handle /retry limit <n> command"""
        try:
            num_value = int(value)
            if num_value < 0:
                LogUtils.error("[*] Invalid number. Use: /retry limit <number> (0 = unlimited)")
                return

            Config.set_runtime_max_retries(num_value)
            display = "UNLIMITED" if num_value == 0 else str(num_value)
            LogUtils.print(f"[*] Max retries set to: {display}")
        except ValueError:
            LogUtils.error("[*] Invalid number. Use: /retry limit <number> (0 = unlimited)")

    def show_current_limit(self) -> None:
        """Show current retry limit"""
        current = Config.effective_max_retries()
        display = "UNLIMITED" if current == 0 else str(current)
        LogUtils.print(f"[*] Current retry limit: {display}")

    def show_help(self) -> None:
        """Show retry command help"""
        help_text = """Usage:
  /retry              Retry the last message
  /retry limit        Show current retry limit
  /retry limit <n>    Set retry limit (0 = unlimited)
  /retry help         Show this help message

Examples:
  /retry              Retry last message
  /retry limit        Show current limit
  /retry limit 3      Set max retries to 3
  /retry limit 0      Unlimited retries

The retry limit controls how many times AI Coder will retry failed API calls.
Exponential backoff is used: 2s, 4s, 8s, 16s, 32s, 64s between retries."""
        LogUtils.print(help_text)
