"""
Council command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class CouncilCommand(BaseCommand):
    """Council command implementation"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "council"
        self._description = "Council command"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return []

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute council command"""
        LogUtils.warn("Council command not yet implemented")
        return CommandResult(should_quit=False, run_api_call=False)
