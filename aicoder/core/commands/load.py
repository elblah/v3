"""
Load command implementation

"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.utils.file_utils import file_exists
from aicoder.utils.json_utils import read_file


class LoadCommand(BaseCommand):
    """Load session from file"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "load"
        self._description = "Load session from file"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def execute(self, args: List[str] = None) -> CommandResult:
        """Load session from file"""
        if args is None:
            args = []

        filename = args[0] if args else "session.json"

        try:
            if not file_exists(filename):
                LogUtils.error(f"Session file not found: {filename}")
                return CommandResult(should_quit=False, run_api_call=False)

            session_data = read_file(filename)

            # Handle both formats: direct array of messages or object with messages property
            messages = (
                session_data
                if isinstance(session_data, list)
                else session_data.get("messages", [])
            )

            if messages and isinstance(messages, list):
                self.context.message_history.set_messages(messages)
                LogUtils.success(f"Session loaded from {filename}")
            else:
                LogUtils.error("Invalid session file format")
        except Exception as e:
            LogUtils.error(f"Error loading session: {e}")

        return CommandResult(should_quit=False, run_api_call=False)
