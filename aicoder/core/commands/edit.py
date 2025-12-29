"""
Edit command - Create new message in $EDITOR

"""

import os
import subprocess
import secrets
from aicoder.core.commands.base import BaseCommand, CommandResult, CommandContext
from aicoder.utils.log import LogUtils, LogOptions
from aicoder.utils.temp_file_utils import create_temp_file
from aicoder.core.config import Config
from aicoder.core import prompt_history


class EditCommand(BaseCommand):
    """Create new message in $EDITOR"""

    def __init__(self, context: CommandContext):
        super().__init__(context)

    def get_name(self) -> str:
        return "edit"

    def get_description(self) -> str:
        return "Create new message in $EDITOR"

    def get_aliases(self):
        return ["e"]

    def execute(self, args: list = None) -> CommandResult:
        """Edit prompt in tmux"""
        try:
            # Check if in tmux (using TMUX env var, not TMUX_PANE)
            if not os.environ.get("TMUX"):
                LogUtils.print(
                    f"{Config.colors['red']}This command only works inside a tmux environment.{Config.colors['reset']}"
                )
                LogUtils.print(
                    f"{Config.colors['yellow']}Please run this command inside tmux.{Config.colors['reset']}"
                )
                return CommandResult(should_quit=False, run_api_call=False)

            # Get editor from environment or default to nano
            editor = os.environ.get("EDITOR", "nano")

            # Create temporary file
            random_suffix = secrets.token_hex(4)
            temp_file = create_temp_file(f"aicoder-edit-{random_suffix}", ".md")

            # Write empty file
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write("")

            LogUtils.print(
                f"Opening {editor} in tmux window...",
                LogOptions(color=Config.colors["cyan"]),
            )
            LogUtils.print(
                "Save and exit when done. The editor is running in a separate tmux window.",
                LogOptions(color=Config.colors["dim"]),
            )

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
            except:
                pass

            if content:
                # Check if content starts with a command (starts with /)
                if content.strip().startswith("/"):
                    # It's a command - execute it instead of sending to AI
                    LogUtils.print(
                        "Command composed.", LogOptions(color=Config.colors["green"])
                    )
                    LogUtils.print(
                        "--- Command ---", LogOptions(color=Config.colors["cyan"])
                    )
                    LogUtils.print(content, LogOptions())
                    LogUtils.print(
                        "---------------", LogOptions(color=Config.colors["cyan"])
                    )
                    # Return special flag to indicate this is a command to execute
                    return CommandResult(
                        should_quit=False,
                        run_api_call=False,
                        command_to_execute=content
                    )
                else:
                    # It's a regular message - send to AI
                    prompt_history.save_prompt(content)
                    LogUtils.print(
                        "Message composed.", LogOptions(color=Config.colors["green"])
                    )
                    LogUtils.print(
                        "--- Message ---", LogOptions(color=Config.colors["cyan"])
                    )
                    LogUtils.print(content, LogOptions())
                    LogUtils.print(
                        "---------------", LogOptions(color=Config.colors["cyan"])
                    )
                    # Return message to trigger AI call
                    return CommandResult(
                        should_quit=False, run_api_call=True, message=content
                    )
            else:
                LogUtils.print(
                    "Empty message - cancelled.",
                    LogOptions(color=Config.colors["yellow"]),
                )
                return CommandResult(should_quit=False, run_api_call=False)

        except Exception as e:
            LogUtils.error(f"Error with editor: {e}")
            return CommandResult(should_quit=False, run_api_call=False)

        finally:
            # Ensure temp file cleanup
            try:
                if "temp_file" in locals() and os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
