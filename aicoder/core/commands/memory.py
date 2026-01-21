"""
Memory command - Export conversation JSON to temp file, edit with $EDITOR, then reload
"""

import json
import os
import secrets
from aicoder.core.commands.base import BaseCommand, CommandResult, CommandContext
from aicoder.utils.log import LogUtils
from aicoder.utils.temp_file_utils import create_temp_file
from aicoder.core.config import Config


class MemoryCommand(BaseCommand):
    """Edit conversation memory in $EDITOR"""

    def __init__(self, context: CommandContext):
        super().__init__(context)

    def get_name(self) -> str:
        return "memory"

    def get_description(self) -> str:
        return "Edit conversation memory in $EDITOR"

    def get_aliases(self):
        return ["m"]

    def execute(self, args: list = None) -> CommandResult:
        """Export conversation to temp file, edit, and reload"""
        if not Config.in_tmux():
            LogUtils.error("This command only works inside a tmux environment.")
            LogUtils.warn("Please run this command inside tmux.")
            return CommandResult(should_quit=False, run_api_call=False)

        editor = os.environ.get("EDITOR", "nano")
        random_suffix = secrets.token_hex(4)
        temp_file = create_temp_file(f"aicoder-memory-{random_suffix}", ".json")

        try:
            # Get messages from history
            messages = self.context.message_history.get_messages()

            # Convert messages to JSON-serializable format
            messages_dict = []
            for msg in messages:
                msg_dict = {
                    "role": msg.get("role"),
                    "content": msg.get("content") or "",
                }

                # Add tool calls if present
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    msg_dict["tool_calls"] = tool_calls

                # Add tool_call_id if present
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id:
                    msg_dict["tool_call_id"] = tool_call_id

                messages_dict.append(msg_dict)

            # Write messages to temp file as JSON
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(messages_dict, f, indent=2, ensure_ascii=False)

            LogUtils.info(f"Exported {len(messages)} messages to {temp_file}")
            LogUtils.info(f"Opening {editor} in tmux window...")
            LogUtils.dim("Save and exit when done. The editor is running in a separate tmux window.")

            sync_point = f"memory_done_{random_suffix}"
            window_name = f"memory_{random_suffix}"

            # Create tmux window with editor and wait-for sync
            tmux_cmd = f'tmux new-window -n "{window_name}" \'bash -c "{editor} {temp_file}; tmux wait-for -S {sync_point}"\''
            os.system(tmux_cmd)

            # Wait for editor to finish
            os.system(f"tmux wait-for {sync_point}")

            # Check if file still exists
            if not os.path.exists(temp_file):
                LogUtils.error("Session file not found after editing")
                return CommandResult(should_quit=False, run_api_call=False)

            # Load edited messages
            with open(temp_file, "r", encoding="utf-8") as f:
                edited_messages = json.load(f)

            if isinstance(edited_messages, list):
                # Replace messages directly - no special handling needed
                self.context.message_history.set_messages(edited_messages)

                LogUtils.success(f"Reloaded {len(edited_messages)} messages from editor")
            else:
                LogUtils.error("Invalid session file format")

            # Clean up temp file
            try:
                os.unlink(temp_file)
            except Exception:
                pass

        except Exception as error:
            LogUtils.error(f"Memory edit failed: {error}")
            # Clean up temp file on error
            try:
                os.unlink(temp_file)
            except Exception:
                pass

        return CommandResult(should_quit=False, run_api_call=False)
