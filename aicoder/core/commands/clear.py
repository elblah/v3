"""
Clear command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
import os


class ClearCommand(BaseCommand):
    """Clear the conversation history"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "clear"
        self._description = "Clear the conversation history"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def execute(self, args: List[str] = None) -> CommandResult:
        """Clear the conversation history"""
        os.system("clear" if os.name == "posix" else "cls")
        self.context.message_history.clear()
        LogUtils.success("Conversation history cleared.")
        return CommandResult(should_quit=False, run_api_call=False)
