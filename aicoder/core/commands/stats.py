"""
Stats command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class StatsCommand(BaseCommand):
    """Show session statistics"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "stats"
        self._description = "Show session statistics"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def execute(self, args: List[str] = None) -> CommandResult:
        """Show session statistics"""
        self.context.stats.print_stats()

        # Let plugins contribute their own stats lines
        plugin_system = self.context.command_handler.plugin_system if self.context.command_handler else None
        if plugin_system:
            for result in plugin_system.call_hooks("on_stats", self.context.stats) or []:
                lines = result if isinstance(result, list) else [result]
                for line in lines:
                    if line:
                        LogUtils.print(str(line))
        return CommandResult(should_quit=False, run_api_call=False)
