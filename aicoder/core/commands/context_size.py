"""
Context size command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class ContextSizeCommand(BaseCommand):
    """View or change context size"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "context-size"
        self._description = "View or change context size"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["cs"]

    def _parse_size(self, value: str) -> int:
        """Parse size string like '100k', '1.5m', '50000'"""
        value = value.strip().lower()

        if value == "default":
            return Config.default_context_size()

        if value.endswith("k"):
            return int(float(value[:-1]) * 1000)
        if value.endswith("m"):
            return int(float(value[:-1]) * 1000000)

        return int(value)

    def _format_size(self, size: int) -> str:
        """Format size for display"""
        if size >= 1000000:
            return f"{size / 1000000:.1f}m"
        elif size >= 1000:
            return f"{size / 1000:.1f}k"
        return str(size)

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute context-size command"""
        current_size = Config.context_size()

        if not args:
            # Show current status
            LogUtils.print(f"Current context size: {self._format_size(current_size)} tokens ({current_size:,})", color="cyan")
            LogUtils.dim("Usage: /cs <size> | Examples: /cs 100k, /cs 1.5m, /cs 50000, /cs default")
            return CommandResult(should_quit=False, run_api_call=False)

        value = args[0]

        try:
            new_size = self._parse_size(value)
        except (ValueError, IndexError):
            LogUtils.printc("Invalid size format. Use: 100k, 1.5m, 50000, or 'default'", color="red")
            return CommandResult(should_quit=False, run_api_call=False)
        except Exception:
            LogUtils.printc("Invalid size format. Use: 100k, 1.5m, 50000, or 'default'", color="red")
            return CommandResult(should_quit=False, run_api_call=False)

        # Validate range
        if new_size < 1000:
            LogUtils.error("Context size too small. Minimum: 1k (1000 tokens)")
            return CommandResult(should_quit=False, run_api_call=False)

        if new_size > 10000000:
            LogUtils.error("Context size too large. Maximum: 10m (10,000,000 tokens)")
            return CommandResult(should_quit=False, run_api_call=False)

        # Set new size
        old_size = current_size
        Config.set_context_size(new_size)

        # Show confirmation
        LogUtils.success(f"Context size changed: {self._format_size(old_size)} → {self._format_size(new_size)}")

        # Recalculate context estimate
        if hasattr(self.context, 'message_history') and self.context.message_history:
            self.context.message_history.estimate_context()

        return CommandResult(should_quit=False, run_api_call=False)
