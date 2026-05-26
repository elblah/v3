"""
Edit command - Create new message in $EDITOR

"""

import os
import shutil
import subprocess
from aicoder.core.commands.base import BaseCommand, CommandResult, CommandContext
from aicoder.utils.log import LogUtils
from aicoder.utils.temp_file_utils import create_temp_file
from aicoder.core import prompt_history


def _gen_token():
    """Generate random hex token - lazy import to avoid 50ms startup cost"""
    import secrets
    return secrets.token_hex(4)


class EditCommand(BaseCommand):
    """Create new message in $EDITOR"""

    def __init__(self, context: CommandContext):
        super().__init__(context)

    def get_name(self) -> str:
        return "edit"

    def get_description(self) -> str:
        return "Create new message in $EDITOR (use 'last' to edit previous message)"

    def get_aliases(self):
        return ["e"]

    def execute(self, args: list = None) -> CommandResult:
        """Edit prompt in tmux"""
        try:
            # Check if in tmux (using TMUX env var, not TMUX_PANE)
            if not os.environ.get("TMUX"):
                LogUtils.error("This command only works inside a tmux environment.")
                LogUtils.warn("Please run this command inside tmux.")
                return CommandResult(should_quit=False, run_api_call=False)

            # Determine initial content
            initial_content = ""
            
            # Determine initial content and editor
            initial_content = ""
            editor = os.environ.get("EDITOR", "nano")

            if args:
                if len(args) == 1:
                    # Single arg - check if it's "last" or a valid editor
                    arg = args[0]
                    if arg == "last":
                        pass  # handled below
                    elif shutil.which(arg):
                        editor = arg  # valid editor found
                else:
                    # Multiple args - treat all as initial content
                    initial_content = " ".join(args)
                    LogUtils.info("Pre-populating with input text...")

            # Create temporary file
            random_suffix = _gen_token()
            temp_file = create_temp_file(f"aicoder-edit-{random_suffix}", ".md")

            # Handle /e last - populate from last user message
            if args and len(args) == 1 and args[0] == "last":
                messages = self.context.message_history.get_messages()
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            initial_content = content
                        elif isinstance(content, dict) and "text" in content:
                            initial_content = content["text"]
                        break
                if initial_content:
                    LogUtils.info("Pre-populating with last user message...")

            # Write initial content to file
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(initial_content)

            LogUtils.info(f"Opening {editor} in tmux window...")
            LogUtils.dim("Save and exit when done. The editor is running in a separate tmux window.")

            # Use tmux wait-for
            sync_point = f"edit_done_{random_suffix}"
            window_name = f"edit_{random_suffix}"

            # Create tmux command that waits for sync point
            tmux_cmd = f'tmux new-window -n "{window_name}" \'bash -c "{editor} {temp_file}; tmux wait-for -S {sync_point}"\''

            # Execute tmux command
            result = subprocess.run(
                tmux_cmd, shell=True, capture_output=True, text=True
            )
            if result.returncode != 0:
                raise Exception(f"tmux command failed: {result.stderr}")

            # Wait for sync point
            wait_cmd = f"tmux wait-for {sync_point}"
            result = subprocess.run(
                wait_cmd, shell=True, capture_output=True, text=True
            )
            if result.returncode != 0:
                raise Exception(f"tmux wait failed: {result.stderr}")

            # Read edited content
            try:
                with open(temp_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
            except FileNotFoundError:
                raise Exception("Edit file not found")

            # Clean up temp file
            try:
                os.remove(temp_file)
            except Exception:
                pass

            if content:
                # Check if content starts with a command (starts with /)
                if content.strip().startswith("/"):
                    # It's a command - execute it instead of sending to AI
                    LogUtils.success("Command composed.")
                    LogUtils.info("--- Command ---")
                    LogUtils.print(content)
                    LogUtils.info("---------------")
                    # Return special flag to indicate this is a command to execute
                    return CommandResult(
                        should_quit=False,
                        run_api_call=False,
                        command_to_execute=content
                    )
                else:
                    # It's a regular message - send to AI
                    prompt_history.save_prompt(content)
                    LogUtils.success("Message composed.")
                    LogUtils.info("--- Message ---")
                    LogUtils.print(content)
                    LogUtils.info("---------------")
                    # Return message to trigger AI call
                    return CommandResult(
                        should_quit=False, run_api_call=True, message=content
                    )
            else:
                LogUtils.warn("Empty message - cancelled.")
                return CommandResult(should_quit=False, run_api_call=False)

        except Exception as e:
            LogUtils.error(f"Error with editor: {e}")
            return CommandResult(should_quit=False, run_api_call=False)

        finally:
            # Ensure temp file cleanup
            try:
                if "temp_file" in locals() and os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass
