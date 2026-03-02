"""
Clipboard Plugin - Copy last message to clipboard or paste clipboard content into editor

Commands:
- /clipboard copy - Copy last message to system clipboard (uses xsel)
- /clipboard paste - Open clipboard content in $EDITOR, edit and send as message
- /clipboard help - Show available subcommands

Requirements:
- xsel must be installed
- For /paste: tmux must be running
"""

import os
import subprocess
import secrets
from typing import Optional

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.utils.temp_file_utils import create_temp_file
from aicoder.core import prompt_history


def create_plugin(ctx):
    """Clipboard plugin - copy to clipboard or paste from clipboard into editor"""

    colors = Config.colors

    def print_color(color_name: str, text: str) -> None:
        """Print text with color"""
        color_code = colors.get(color_name, "")
        LogUtils.print(f"{color_code}{text}{colors['reset']}")

    def get_last_message() -> Optional[str]:
        """Get the last message from message history"""
        if not ctx.app or not ctx.app.message_history:
            return None

        messages = ctx.app.message_history.get_messages()
        if not messages:
            return None

        # Get last non-system message
        for msg in reversed(messages):
            if msg.get("role") != "system":
                return msg.get("content", "")

        return None

    def copy_to_clipboard(text: str) -> tuple[bool, str]:
        """Copy text to system clipboard using xsel"""
        if not text:
            return False, "No text to copy"

        if not subprocess.run(["xsel", "--version"], capture_output=True).returncode == 0:
            return False, "xsel not installed"

        try:
            proc = subprocess.Popen(
                ["xsel", "--clipboard", "--input"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            _, stderr = proc.communicate(input=text.encode('utf-8'), timeout=5)
            if proc.returncode == 0:
                return True, "Copied to clipboard"
            else:
                err = stderr.decode('utf-8', errors='ignore').strip()
                return False, f"xsel failed: {err}" if err else "xsel failed"
        except subprocess.TimeoutExpired:
            proc.kill()
            return False, "xsel timed out after 5s"
        except Exception as e:
            return False, f"xsel error: {str(e)}"

    def get_clipboard_content() -> tuple[bool, str]:
        """Get content from system clipboard using xsel"""
        if not subprocess.run(["xsel", "--version"], capture_output=True).returncode == 0:
            return False, "xsel not installed"

        try:
            result = subprocess.run(
                ["xsel", "--clipboard", "--output"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                err = result.stderr.strip()
                return False, f"xsel failed: {err}" if err else "xsel failed"
        except subprocess.TimeoutExpired:
            return False, "xsel timed out after 5s"
        except Exception as e:
            return False, f"xsel error: {str(e)}"

    def handle_paste() -> None:
        """Open clipboard content in $EDITOR, wait for edit, send as message"""
        # Check if in tmux
        if not os.environ.get("TMUX"):
            print_color("yellow", "[!] This command only works inside tmux")
            print_color("cyan", "[i] Please run this command inside tmux")
            return

        # Get clipboard content
        success, content = get_clipboard_content()
        if not success:
            print_color("yellow", f"[!] {content}")
            return

        if not content:
            print_color("yellow", "[!] Clipboard is empty")
            return

        # Get editor from environment or default to nano
        editor = os.environ.get("EDITOR", "nano")

        # Create temporary file
        random_suffix = secrets.token_hex(4)
        temp_file = create_temp_file(f"aicoder-clipboard-{random_suffix}", ".md")

        try:
            # Write clipboard content to file
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(content)

            print_color("brightGreen", f"[*] Opening {editor} in tmux window...")
            LogUtils.print(f"{colors['dim']}Save and exit when done. The editor is running in a separate tmux window.{colors['reset']}")

            # Use tmux wait-for
            sync_point = f"clipboard_done_{random_suffix}"
            window_name = f"clipboard_{random_suffix}"

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
                    edited_content = f.read().strip()
            except FileNotFoundError:
                raise Exception("Edit file not found")

            # Clean up temp file
            try:
                os.remove(temp_file)
            except Exception:
                pass

            if edited_content:
                # Check if content starts with a command (starts with /)
                if edited_content.strip().startswith("/"):
                    # It's a command - execute it instead of sending to AI
                    print_color("brightGreen", "[+] Command composed.")
                    LogUtils.print(f"{colors['cyan']}--- Command ---{colors['reset']}")
                    LogUtils.print(edited_content)
                    LogUtils.print(f"{colors['cyan']}---------------{colors['reset']}")
                    # Execute the command directly
                    if ctx.app and hasattr(ctx.app, 'command_handler'):
                        ctx.app.command_handler.handle_command(edited_content)
                else:
                    # It's a regular message - send to AI
                    prompt_history.save_prompt(edited_content)
                    print_color("brightGreen", "[+] Message composed.")
                    LogUtils.print(f"{colors['cyan']}--- Message ---{colors['reset']}")
                    LogUtils.print(edited_content)
                    LogUtils.print(f"{colors['cyan']}---------------{colors['reset']}")
                    # Add message to history and trigger AI response
                    if ctx.app:
                        ctx.app.add_user_input(edited_content)
                        ctx.app.session_manager.process_with_ai()
            else:
                print_color("yellow", "[!] Empty message - cancelled.")

        except Exception as e:
            print_color("yellow", f"[!] Error with editor: {e}")

        finally:
            # Ensure temp file cleanup
            try:
                if "temp_file" in locals() and os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass

    def handle_clipboard_command(args_str: str) -> None:
        """
        Handle /clipboard command with subcommands

        Usage:
            /clipboard copy - Copy last message to system clipboard
            /clipboard paste - Open clipboard content in $EDITOR
            /clipboard help - Show this help
        """
        args = args_str.strip()

        # Show help if no args or explicit help
        if not args or args == "help":
            print_color("brightGreen", "[*] Clipboard Plugin")
            LogUtils.print()
            LogUtils.print("Usage:")
            LogUtils.print(f"    {colors['cyan']}/clipboard copy{colors['reset']}  - Copy last message to system clipboard")
            LogUtils.print(f"    {colors['cyan']}/clipboard paste{colors['reset']} - Open clipboard content in $EDITOR")
            LogUtils.print(f"    {colors['cyan']}/clipboard help{colors['reset']}  - Show this help")
            LogUtils.print()
            LogUtils.print("Requirements:")
            LogUtils.print(f"    {colors['dim']}- xsel must be installed{colors['reset']}")
            LogUtils.print(f"    {colors['dim']}- For paste: tmux must be running{colors['reset']}")
            return

        # Handle subcommands
        subcommand = args.lower().split()[0]

        if subcommand == "copy":
            last_message = get_last_message()
            if not last_message:
                print_color("yellow", "[!] No messages in history to copy")
                return

            success, msg = copy_to_clipboard(last_message)
            if success:
                print_color("brightGreen", f"[+] {msg}")
            else:
                print_color("yellow", f"[!] {msg}")

        elif subcommand == "paste":
            handle_paste()

        else:
            print_color("yellow", f"[!] Unknown subcommand: {subcommand}")
            print_color("cyan", "[i] Use /clipboard help to see available subcommands")

    # Register the /clipboard command
    ctx.register_command(
        "clipboard",
        handle_clipboard_command,
        "Copy last message to clipboard or paste clipboard content into editor"
    )

    if Config.debug():
        LogUtils.print("  - /clipboard command")
