"""
Markdown Formatter Plugin - Format and display markdown from message history

Usage:
    /mdfmt last  - last assistant message (default)
    /mdfmt 5     - last 5 messages
    /mdfmt all   - all assistant messages
"""

import os
import subprocess
import shutil
from typing import Optional

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    """Markdown formatter plugin"""

    def _get_assistant_messages():
        """Get all assistant messages from history"""
        return [m for m in ctx.app.message_history.messages if m.get("role") == "assistant"]

    def _get_term_width():
        """Get terminal width"""
        cols = os.environ.get("COLUMNS")
        if cols:
            return int(cols) - 4
        try:
            return shutil.get_terminal_size().columns - 4
        except:
            return 96

    def _format_markdown(content: str) -> str:
        """Pass markdown through glow"""
        if not content:
            return ""
        
        width = _get_term_width()
        
        if shutil.which("glow"):
            try:
                result = subprocess.run(
                    ["glow", "-p", "-w", str(width)],
                    input=content,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                pass
        
        return content

    def _format_message(idx: int, msg: dict):
        """Format a single message with header"""
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
        
        if not content:
            return f"{Config.colors['dim']}[Message {idx}] (empty){Config.colors['reset']}\n"
        
        formatted = _format_markdown(content)
        header = f"{Config.colors['cyan']}--- Message {idx} ---{Config.colors['reset']}\n"
        return header + formatted + "\n"

    def mdfmt_handler(args):
        """Handle /mdfmt command"""
        assistant_msgs = _get_assistant_messages()
        
        if not assistant_msgs:
            LogUtils.warn("[*] No assistant messages in history")
            return
        
        if not args:
            # Default: last message
            msg = assistant_msgs[-1]
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
            if content:
                LogUtils.print(_format_markdown(content))
            return
        
        arg = args[0].lower()
        
        # All messages
        if arg in ("all", "a"):
            for i, msg in enumerate(assistant_msgs):
                LogUtils.print(_format_message(i + 1, msg))
            return
        
        # Last N messages (number)
        if arg.isdigit():
            n = int(arg)
            if n > len(assistant_msgs):
                n = len(assistant_msgs)
            if n == 1:
                msg = assistant_msgs[-1]
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
                if content:
                    LogUtils.print(_format_markdown(content))
            else:
                start = len(assistant_msgs) - n
                for i in range(start, len(assistant_msgs)):
                    LogUtils.print(_format_message(i + 1, assistant_msgs[i]))
            return
        
        # Last message explicitly
        if arg in ("last", "l"):
            msg = assistant_msgs[-1]
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
            if content:
                LogUtils.print(_format_markdown(content))
            return
        
        LogUtils.warn(f"[*] Unknown argument: {arg}")
        LogUtils.dim("    Usage: /mdfmt [last|n|all]")
        LogUtils.dim("      /mdfmt     - last message")
        LogUtils.dim("      /mdfmt last - last message")
        LogUtils.dim("      /mdfmt 5    - last 5 messages")
        LogUtils.dim("      /mdfmt all  - all messages")

    ctx.register_command("mdfmt", mdfmt_handler, "Format markdown in message history")