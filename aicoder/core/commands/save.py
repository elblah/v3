"""
Save command implementation

"""

from typing import List
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.utils.json_utils import write_file
from aicoder.utils.jsonl_utils import write_file as write_jsonl
from pathlib import Path


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

    def get_aliases(self) -> List[str]:
        return ["s"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Save session to file"""
        if args is None:
            args = []

        filename = args[0] if args else "session.json"

        try:
            messages = self.context.message_history.get_chat_messages()
            
            # Only save if there's at least one real user/assistant message
            # (exclude bare role placeholders like [user], keep [SUMMARY])
            has_real_content = any(
                msg.get("role") in ("user", "assistant")
                and msg.get("content")
                and (
                    not str(msg.get("content", "")).startswith("[")
                    or str(msg.get("content", "")).startswith("[SUMMARY]")
                )
                for msg in messages
            )
            
            if not has_real_content:
                LogUtils.success(f"[*] Skipping save to {filename}: no real user or assistant messages in session")
                return CommandResult(should_quit=False, run_api_call=False)
            
            # Detect format based on file extension
            is_jsonl = Path(filename).suffix.lower() == ".jsonl"
            
            if is_jsonl:
                # Save in JSONL format
                write_jsonl(filename, messages)
                LogUtils.success(f"Session saved to {filename} (JSONL format)")
            else:
                # Save in JSON format (backward compatibility)
                write_file(filename, messages)
                LogUtils.success(f"Session saved to {filename} (JSON format)")
                
        except Exception as e:
            LogUtils.error(f"Error saving session: {e}")

        return CommandResult(should_quit=False, run_api_call=False)
