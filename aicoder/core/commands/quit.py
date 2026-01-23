"""
Quit command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class QuitCommand(BaseCommand):
    """Exit the application"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "quit"
        self._description = "Exit the application"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["q"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Exit the application with session save"""
        LogUtils.success("Goodbye!")
        # Trigger immediate shutdown (will call shutdown method via main loop)
        return CommandResult(should_quit=True, run_api_call=False)
