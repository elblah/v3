"""
Retry command implementation
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class RetryCommand(BaseCommand):
    """Retry the last message by resending all current messages"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "retry"
        self._description = "Retry the last message by resending all current messages"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["r"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Retry the last message"""
        LogUtils.print("[*] Retrying last request...")

        # Return with run_api_call: true to trigger another API call with same messages
        # The last message will be resent exactly as it was
        return CommandResult(should_quit=False, run_api_call=True)
