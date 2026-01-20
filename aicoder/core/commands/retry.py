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

        # Handle /retry max_backoff [n]
        if len(args) >= 1 and args[0].lower() == "max_backoff":
            if len(args) >= 2:
                self.handle_max_backoff(args[1])
            else:
                self.show_current_max_backoff()
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

    def handle_max_backoff(self, value: str) -> None:
        """Handle /retry max_backoff <n> command"""
        try:
            num_value = int(value)
            if num_value < 1:
                LogUtils.error("[*] Invalid number. Use: /retry max_backoff <seconds> (minimum: 1)")
                return

            Config.set_runtime_max_backoff(num_value)
            LogUtils.print(f"[*] Max backoff set to: {num_value}s")
        except ValueError:
            LogUtils.error("[*] Invalid number. Use: /retry max_backoff <seconds> (minimum: 1)")

    def show_current_max_backoff(self) -> None:
        """Show current max backoff"""
        current = Config.effective_max_backoff()
        LogUtils.print(f"[*] Current max backoff: {current}s")

    def show_help(self) -> None:
        """Show retry command help"""
        current_limit = Config.effective_max_retries()
        current_backoff = Config.effective_max_backoff()
        limit_display = "UNLIMITED" if current_limit == 0 else str(current_limit)
        
        help_text = f"""Usage:
  /retry              Retry the last message
  /retry limit        Show current retry limit
  /retry limit <n>    Set retry limit (0 = unlimited)
  /retry max_backoff        Show current max backoff
  /retry max_backoff <n>    Set max backoff in seconds
  /retry help         Show this help message

Current Settings:
  Max retries: {limit_display}
  Max backoff: {current_backoff}s

Examples:
  /retry              Retry last message
  /retry limit        Show current limit
  /retry limit 3      Set max retries to 3
  /retry limit 0      Unlimited retries
  /retry max_backoff  Show current max backoff
  /retry max_backoff 120 Set max backoff to 120s

The retry limit controls how many times AI Coder will retry failed API calls.
Exponential backoff is used: 2s, 4s, 8s, 16s, 32s, max_backoff between retries.

Environment Variables:
  MAX_RETRIES=<n>         Set default retry limit (default: 10)
  MAX_BACKOFF_SECONDS=<n> Set default max backoff in seconds (default: 64)"""
        LogUtils.print(help_text)
