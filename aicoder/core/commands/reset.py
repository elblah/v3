"""
Reset command - Reset the entire session
Ported exactly from TypeScript version
"""

from typing import List

from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class ResetCommand(BaseCommand):
    """Reset command for clearing the session"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "reset"
        self._description = "Reset the entire session"

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        return self._description

    def get_aliases(self) -> List[str]:
        return []

    def execute(self, args: List[str] = None) -> CommandResult:
        self.context.message_history.clear()
        self.context.stats.reset()
        LogUtils.success("Session reset. Starting fresh.")
        return CommandResult(should_quit=False, run_api_call=False)
