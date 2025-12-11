"""
Memory command - Export conversation JSON to temp file, edit with $EDITOR, then reload
"""

import json
import os
import secrets
import time
from aicoder.core.commands.base import BaseCommand, CommandResult, CommandContext
from aicoder.utils.log import LogUtils, LogOptions
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
                    # tool_calls should already be dicts, no need for __dict__
                    msg_dict["tool_calls"] = tool_calls

                # Add tool_call_id if present
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id:
                    msg_dict["tool_call_id"] = tool_call_id

                messages_dict.append(msg_dict)

            # Write messages to temp file as JSON
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(messages_dict, f, indent=2, ensure_ascii=False)

            LogUtils.print(
                f"Exported {len(messages)} messages to {temp_file}",
                LogOptions(color=Config.colors["cyan"]),
            )
            LogUtils.print(
                f"Opening {editor} in tmux window...",
                LogOptions(color=Config.colors["cyan"]),
            )
            LogUtils.print(
                "Save and exit when done. The editor is running in a separate tmux window.",
                LogOptions(color=Config.colors["dim"]),
            )

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
                # Clear existing history
                self.context.message_history.clear()

                # Reload messages
                for msg in edited_messages:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    tool_calls = msg.get("tool_calls")
                    tool_call_id = msg.get("tool_call_id")

                    if role == "system":
                        self.context.message_history.add_system_message(content)
                    elif role == "user":
                        self.context.message_history.add_user_message(content)
                    elif role == "assistant":
                        from aicoder.type_defs.message_types import AssistantMessage

                        self.context.message_history.add_assistant_message(
                            AssistantMessage(content=content, tool_calls=tool_calls)
                        )
                    elif role == "tool":
                        self.context.message_history.add_tool_results(
                            [
                                {
                                    "content": content,
                                    "tool_call_id": tool_call_id,
                                }
                            ]
                        )
                    else:
                        LogUtils.warn(
                            f"Warning: Unknown message role '{role}', treating as user"
                        )
                        self.context.message_history.add_user_message(content)

                LogUtils.success(
                    f"Reloaded {len(edited_messages)} messages from editor"
                )
            else:
                LogUtils.error("Invalid session file format")

            # Clean up temp file
            try:
                os.unlink(temp_file)
            except:
                pass

        except Exception as error:
            LogUtils.error(f"Memory edit failed: {error}")
            # Clean up temp file on error
            try:
                os.unlink(temp_file)
            except:
                pass

        return CommandResult(should_quit=False, run_api_call=False)
