"""
Load command implementation

"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.utils.log import LogUtils
from aicoder.utils.file_utils import file_exists
from aicoder.utils.json_utils import read_file
from aicoder.utils.jsonl_utils import read_file as read_jsonl
from pathlib import Path


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

    def get_aliases(self) -> List[str]:
        return ["l"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Load session from file"""
        if args is None:
            args = []

        filename = args[0] if args else "session.json"
        
        # Handle special case: /load last
        if filename == "last":
            if file_exists("last"):
                filename = "last"
            elif file_exists(".aicoder/last-session.json"):
                filename = ".aicoder/last-session.json"
            else:
                LogUtils.error("No 'last' file found in current directory or .aicoder/last-session.json")
                return CommandResult(should_quit=False, run_api_call=False)

        # Call session change hooks before loading new session (allows plugins to cleanup state)
        self.context.command_handler.plugin_system.call_hooks("on_session_change")

        try:
            if not file_exists(filename):
                LogUtils.error(f"Session file not found: {filename}")
                return CommandResult(should_quit=False, run_api_call=False)

            # Detect format based on file extension
            is_jsonl = Path(filename).suffix.lower() == ".jsonl"
            
            if is_jsonl:
                # Load JSONL format
                messages = read_jsonl(filename)
                if messages and isinstance(messages, list):
                    self.context.message_history.set_messages(messages)
                    LogUtils.success(f"Session loaded from {filename} (JSONL format)")
                else:
                    LogUtils.error("Invalid JSONL session file format")
            else:
                # Load JSON format (backward compatibility)
                session_data = read_file(filename)

                # Handle both formats: direct array of messages or object with messages property
                messages = (
                    session_data
                    if isinstance(session_data, list)
                    else session_data.get("messages", [])
                )

                if messages and isinstance(messages, list):
                    self.context.message_history.set_messages(messages)
                    LogUtils.success(f"Session loaded from {filename} (JSON format)")
                else:
                    LogUtils.error("Invalid JSON session file format")
                    
        except Exception as e:
            LogUtils.error(f"Error loading session: {e}")

        return CommandResult(should_quit=False, run_api_call=False)
