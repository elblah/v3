"""
Copy Plugin - Copy last message to clipboard or tmux buffer

Commands:
- /copy clipboard (or /copy clip) - Copy last message to system clipboard
- /copy tmux - Copy last message to tmux buffer
- /copy help - Show available subcommands

Requirements:
- For clipboard: xclip, wl-copy, or pbcopy (macOS)
- For tmux: tmux must be running
"""

import subprocess
import shutil
from typing import Optional

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    """Copy plugin - copy last message to clipboard or tmux buffer"""

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
        """Copy text to system clipboard using available tool"""
        if not text:
            return False, "No text to copy"

        # Try different clipboard tools
        tools = [
            (["xsel", "--clipboard", "--input"], "xsel"),
            (["xclip", "-selection", "clipboard"], "xclip"),
            (["wl-copy"], "wl-clipboard"),
            (["pbcopy"], "pbcopy"),  # macOS
        ]

        errors = []
        for cmd, tool_name in tools:
            if shutil.which(cmd[0]):
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    _, stderr = proc.communicate(input=text.encode('utf-8'), timeout=5)
                    if proc.returncode == 0:
                        return True, f"Copied to clipboard using {tool_name}"
                    else:
                        err = stderr.decode('utf-8', errors='ignore').strip()
                        if err:
                            errors.append(f"{tool_name}: {err.split(chr(10))[0]}")
                except subprocess.TimeoutExpired:
                    proc.kill()
                    errors.append(f"{tool_name}: timed out after 5s")
                except Exception as e:
                    errors.append(f"{tool_name}: {str(e)}")

        if errors:
            return False, "Clipboard tools failed:\n  - " + "\n  - ".join(errors)
        return False, "No clipboard tool found (install xclip, xsel, wl-clipboard, or use macOS)"

    def copy_to_tmux(text: str) -> tuple[bool, str]:
        """Copy text to tmux buffer"""
        if not text:
            return False, "No text to copy"

        # Check if tmux is available and we're in a tmux session
        if not shutil.which("tmux"):
            return False, "tmux not installed"

        # Check if we're in a tmux session
        if not subprocess.run(
            ["tmux", "display-message", "-p", "#S"],
            capture_output=True,
            text=True
        ).returncode == 0:
            return False, "Not running inside tmux"

        try:
            # Use tmux load-buffer with stdin
            proc = subprocess.Popen(
                ["tmux", "load-buffer", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            proc.communicate(input=text.encode('utf-8'))
            if proc.returncode == 0:
                return True, "Copied to tmux buffer (use Ctrl+b ] to paste)"
        except Exception as e:
            return False, f"Failed to copy to tmux: {e}"

        return False, "Failed to copy to tmux buffer"

    def handle_copy_command(args_str: str) -> None:
        """
        Handle /copy command with subcommands

        Usage:
            /copy clipboard (or /copy clip) - Copy last message to clipboard
            /copy tmux - Copy last message to tmux buffer
            /copy help - Show this help
        """
        args = args_str.strip()

        # Show help if no args or explicit help
        if not args or args == "help":
            print_color("brightGreen", "[*] Copy Plugin - Copy last message")
            LogUtils.print()
            LogUtils.print("Usage:")
            LogUtils.print(f"    {colors['cyan']}/copy clipboard{colors['reset']}  - Copy last message to system clipboard")
            LogUtils.print(f"    {colors['cyan']}/copy clip{colors['reset']}       - Shortcut for clipboard")
            LogUtils.print(f"    {colors['cyan']}/copy tmux{colors['reset']}       - Copy last message to tmux buffer")
            LogUtils.print(f"    {colors['cyan']}/copy help{colors['reset']}       - Show this help")
            LogUtils.print()
            LogUtils.print("Requirements:")
            LogUtils.print("    - Clipboard: xclip, xsel, wl-clipboard, or pbcopy (macOS)")
            LogUtils.print("    - Tmux: tmux must be running")
            return

        # Get last message
        last_message = get_last_message()
        if not last_message:
            print_color("yellow", "[!] No messages in history to copy")
            return

        # Handle subcommands
        subcommand = args.lower().split()[0]

        if subcommand in ("clipboard", "clip"):
            success, msg = copy_to_clipboard(last_message)
            if success:
                print_color("brightGreen", f"[+] {msg}")
            else:
                print_color("yellow", f"[!] {msg}")

        elif subcommand == "tmux":
            success, msg = copy_to_tmux(last_message)
            if success:
                print_color("brightGreen", f"[+] {msg}")
            else:
                print_color("yellow", f"[!] {msg}")

        else:
            print_color("yellow", f"[!] Unknown subcommand: {subcommand}")
            print_color("cyan", "[i] Use /copy help to see available subcommands")

    # Register the /copy command
    ctx.register_command(
        "copy",
        handle_copy_command,
        "Copy last message to clipboard or tmux buffer"
    )

    if Config.debug():
        LogUtils.print("  - /copy command")
