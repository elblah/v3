"""
New command - Reset the entire session (formerly reset)
Ported exactly from TypeScript version
"""

from typing import List

from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class NewCommand(BaseCommand):
    """New command for resetting the session (formerly /reset)"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "new"
        self._description = "Reset the entire session"

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        return self._description

    def get_aliases(self) -> List[str]:
        return ["n"]

    def execute(self, args: List[str] = None) -> CommandResult:
        # Reset stats first (this clears prompt size)
        self.context.stats.reset()
        # Then clear message history (this preserves system prompt and recalculates prompt size)
        self.context.message_history.clear()
        LogUtils.success("Session reset. Starting fresh.")
        return CommandResult(should_quit=False, run_api_call=False)