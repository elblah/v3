"""
Over Plugin - Radio protocol: detect cut-off AI responses via [OVER] tag

When enabled, appends a system-reminder to every user message telling the AI
to end with [OVER]. After AI responds, checks for [OVER]. If missing (cut-off),
auto-retries with "continue" prompt (like empty_retry pattern).

Usage:
  /over on      Enable [OVER] protocol
  /over off     Disable [OVER] protocol
  /over status  Show current state
"""

import os
from typing import Optional

from aicoder.utils.log import LogUtils
from aicoder.core.config import Config


OVER_TAG = "[OVER]"
OVER_INSTRUCTION = (
    "\n\n<system-reminder>\n"
    "IMPORTANT: YOUR RESPONSE MUST CONTAIN [OVER] SOMEWHERE.\n"
    "Any line, any position — just have [OVER] in the text.\n"
    "If missing, system assumes response was cut off and will retry.\n"
    "THIS IS A RADIO PROTOCOL. DO NOT FORGET.\n"
    "</system-reminder>"
)
CONTINUE_PROMPT = (
    "Your previous response was cut off (missing [OVER] tag). "
    "Continue exactly where you left off. "
    "Your response MUST contain [OVER] somewhere — any line, any position."
)


class OverService:
    _enabled: bool = False
    _retry_count: int = 0

    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled

    @classmethod
    def set_enabled(cls, enabled: bool) -> None:
        cls._enabled = enabled
        if not enabled:
            cls._retry_count = 0

    @classmethod
    def get_retry_count(cls) -> int:
        return cls._retry_count

    @classmethod
    def increment_retry(cls) -> None:
        cls._retry_count += 1

    @classmethod
    def reset_retry(cls) -> None:
        cls._retry_count = 0


class OverCommand:
    def __init__(self, app):
        self.app = app

    def handle_over(self, args_str: str) -> str:
        args = args_str.strip().lower().split()

        if not args or args[0] == "help":
            status = "enabled" if OverService.is_enabled() else "disabled"
            count = OverService.get_retry_count()
            return (
                f"[OVER] protocol: {status}, retries: {count}\n\n"
                "Commands: /over on | /over off | /over status"
            )

        if args[0] == "on":
            OverService.set_enabled(True)
            return "[OVER] protocol enabled. AI will be instructed to end responses with [OVER]."

        if args[0] == "off":
            OverService.set_enabled(False)
            return "[OVER] protocol disabled."

        if args[0] == "status":
            status = "enabled" if OverService.is_enabled() else "disabled"
            count = OverService.get_retry_count()
            return f"[OVER] protocol: {status}, retries so far: {count}"

        return f"Unknown subcommand: {args[0]}. Use 'on', 'off', or 'status'."

    def on_user_prompt(self, user_input: str) -> Optional[str]:
        """Append [OVER] instruction to user message when enabled"""
        if not OverService.is_enabled():
            return None
        # Don't append to commands
        if user_input.strip().startswith("/"):
            return None
        return user_input + OVER_INSTRUCTION

    def on_after_ai_processing(self, has_tool_calls: bool) -> Optional[str]:
        """Check if AI ended with [OVER]. If not, auto-retry. Strip [OVER] from history."""
        if not OverService.is_enabled():
            return None

        # Don't override if another plugin already set next_prompt
        if self.app.has_next_prompt():
            return None

        # Tool calls in progress = not done yet, don't check
        if has_tool_calls:
            return None

        # Get last assistant message from history
        if not self.app.message_history:
            return None

        messages = self.app.message_history.get_messages()
        last_assistant = None

        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                last_assistant = msg
                break

        if last_assistant is None:
            return None

        content = last_assistant.get("content", "")

        # Check if [OVER] appears anywhere in the response
        if OVER_TAG in content:
            # Strip [OVER] from stored message
            last_assistant["content"] = content.replace(OVER_TAG, "").rstrip()
            OverService.reset_retry()
            return None

        # Missing [OVER] - likely cut off, retry
        OverService.increment_retry()
        count = OverService.get_retry_count()

        LogUtils.warn(f"[OVER] Response missing [OVER] tag (retry #{count})")
        return CONTINUE_PROMPT


def create_plugin(ctx):
    """Over plugin - radio protocol for cut-off detection"""
    cmd = OverCommand(ctx.app)

    # Check env var
    if os.environ.get("OVER") == "1":
        OverService.set_enabled(True)

    # Register command
    ctx.register_command("/over", lambda args: cmd.handle_over(args))

    # Register hooks
    ctx.register_hook("after_user_prompt", cmd.on_user_prompt)
    ctx.register_hook("after_ai_processing", cmd.on_after_ai_processing)

    if Config.debug():
        LogUtils.print("[+] Over plugin loaded")
        status = "ON" if OverService.is_enabled() else "off"
        LogUtils.print(f"    - /over command (status: {status})")

    return {}
