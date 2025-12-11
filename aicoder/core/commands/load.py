"""
Load command implementation
Ported exactly from TypeScript version
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
        """Load session from file - ported exactly from TS"""
        if args is None:
            args = []

        filename = args[0] if args else "session.json"

        try:
            if not file_exists(filename):
                LogUtils.error(f"Session file not found: {filename}")
                return CommandResult(should_quit=False, run_api_call=False)

            # Use json_utils.read_file like TypeScript
            session_data = read_file(filename)

            # Handle both formats: direct array of messages or object with messages property
            messages_raw = (
                session_data
                if isinstance(session_data, list)
                else session_data.get("messages", [])
            )

            if messages_raw and isinstance(messages_raw, list):
                # Convert dictionaries to Message objects (required for Python)
                messages = self._convert_to_message_objects(messages_raw)
                self.context.message_history.set_messages(messages)
                LogUtils.success(f"Session loaded from {filename}")
            else:
                LogUtils.error("Invalid session file format")
        except Exception as e:
            LogUtils.error(f"Error loading session: {e}")

        return CommandResult(should_quit=False, run_api_call=False)

    def _convert_to_message_objects(self, messages_raw):
        """Convert dictionary messages to Message objects"""
        from aicoder.type_defs.message_types import (
            Message,
            MessageRole,
            MessageToolCall,
        )

        messages = []
        for msg_dict in messages_raw:
            role_str = msg_dict.get("role")
            if not role_str:
                continue

            # Validate role is one of the allowed values
            valid_roles = ["system", "user", "assistant", "tool"]
            if role_str not in valid_roles:
                continue

            role = role_str

            # Handle tool calls if present
            tool_calls = None
            if "tool_calls" in msg_dict and msg_dict["tool_calls"]:
                tool_calls = []
                for tc in msg_dict["tool_calls"]:
                    tool_calls.append(
                        MessageToolCall(
                            id=tc.get("id", ""),
                            type=tc.get("type", "function"),
                            function=tc.get("function", {}),
                            index=tc.get("index"),
                        )
                    )

            message = Message(
                role=role,
                content=msg_dict.get("content"),
                tool_calls=tool_calls,
                tool_call_id=msg_dict.get("tool_call_id"),
            )
            messages.append(message)

        return messages
