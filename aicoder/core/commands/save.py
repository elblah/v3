"""
Save command implementation
Ported exactly from TypeScript version
"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.utils.json_utils import write_file


class SaveCommand(BaseCommand):
    """Save current session to file"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "save"
        self._description = "Save current session to file"

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def execute(self, args: List[str] = None) -> CommandResult:
        """Save session to file - ported exactly from TS"""
        if args is None:
            args = []

        filename = args[0] if args else "session.json"

        try:
            messages = self.context.message_history.get_messages()

            # Convert Message objects to dictionaries for JSON serialization
            session_data = [self._message_to_dict(msg) for msg in messages]

            write_file(filename, session_data)
            LogUtils.success(f"Session saved to {filename}")
        except Exception as e:
            LogUtils.error(f"Error saving session: {e}")

        return CommandResult(should_quit=False, run_api_call=False)

    def _message_to_dict(self, message) -> dict:
        """Convert Message object to dictionary for JSON serialization"""
        result = {"role": message.get("role"), "content": message.get("content")}

        if hasattr(message, "tool_calls") and message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": tc.function,
                    "index": tc.index,
                }
                for tc in message.tool_calls
            ]

        if hasattr(message, "tool_call_id") and message.tool_call_id:
            result["tool_call_id"] = message.tool_call_id

        return result
