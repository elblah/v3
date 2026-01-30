"""
Empty Retry Plugin - Detects empty AI responses and retries forever with delay

When AI returns empty message (no content, no tool calls), automatically
retries with a nudge after a 10-second delay.
"""

import time
from typing import Optional

from aicoder.utils.log import LogUtils
from aicoder.core.config import Config


class EmptyRetryService:
    """Service for empty message retry logic"""

    _enabled: bool = True
    _delay_seconds: int = 10
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
    def get_delay(cls) -> int:
        return cls._delay_seconds

    @classmethod
    def set_delay(cls, seconds: int) -> None:
        cls._delay_seconds = max(1, seconds)

    @classmethod
    def get_retry_count(cls) -> int:
        return cls._retry_count

    @classmethod
    def increment_retry(cls) -> None:
        cls._retry_count += 1

    @classmethod
    def reset_retry(cls) -> None:
        cls._retry_count = 0


class EmptyRetryCommand:
    """Command handler for empty retry plugin"""

    def __init__(self, app):
        self.app = app

    def show_help(self) -> str:
        return """
Empty Retry Plugin - Auto-retry on empty AI responses

Usage:
  /r                    Trigger retry manually (same as empty detection)
  /empty-retry on       Enable auto-retry
  /empty-retry off      Disable auto-retry
  /empty-retry delay N  Set delay in seconds (default: 10)
  /empty-retry status   Show current settings

How it works:
  When AI returns empty response (no text, no tool calls), the plugin
  automatically waits 10 seconds and retries with a nudge message.
  This continues forever until AI responds or you disable it.
"""

    def handle_r(self, args_str: str) -> str:
        """Handle /r command - manual retry"""
        EmptyRetryService.increment_retry()
        delay = EmptyRetryService.get_delay()

        LogUtils.warn(f"[EMPTY-RETRY] Manual retry triggered... retrying in {delay}s")
        time.sleep(delay)

        return "The user is waiting for your response. Please provide a helpful answer."

    def handle_empty_retry(self, args_str: str) -> str:
        """Handle /empty-retry command"""
        args = args_str.strip().lower().split()

        if not args or args[0] == "help":
            return self.show_help()

        if args[0] == "on":
            EmptyRetryService.set_enabled(True)
            return "Empty retry enabled."

        if args[0] == "off":
            EmptyRetryService.set_enabled(False)
            return "Empty retry disabled."

        if args[0] == "status":
            status = "enabled" if EmptyRetryService.is_enabled() else "disabled"
            delay = EmptyRetryService.get_delay()
            count = EmptyRetryService.get_retry_count()
            return f"Empty retry: {status}, delay: {delay}s, retries so far: {count}"

        if args[0] == "delay" and len(args) >= 2:
            try:
                seconds = int(args[1])
                EmptyRetryService.set_delay(seconds)
                return f"Empty retry delay set to {seconds} seconds."
            except ValueError:
                return f"Error: Invalid delay value '{args[1]}'"

        return f"Unknown command: {args[0]}. Use 'on', 'off', 'delay N', or 'status'."

    def handle_hook(self, has_tool_calls: bool) -> Optional[str]:
        """Hook called after AI processing - detect empty response and retry"""
        if not EmptyRetryService.is_enabled():
            return None

        # If AI made tool calls, it's not empty - reset counter
        if has_tool_calls:
            EmptyRetryService.reset_retry()
            return None

        # Check last assistant message
        if not self.app.message_history:
            return None

        messages = self.app.message_history.get_messages()
        last_assistant_msg = None

        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                last_assistant_msg = content
                break

        # If there's actual content, not empty - reset counter
        if last_assistant_msg and last_assistant_msg.strip():
            EmptyRetryService.reset_retry()
            return None

        # Empty response detected - retry
        EmptyRetryService.increment_retry()
        delay = EmptyRetryService.get_delay()
        count = EmptyRetryService.get_retry_count()

        LogUtils.warn(f"[EMPTY-RETRY] Empty message detected (retry #{count})... retrying in {delay}s")
        time.sleep(delay)

        return "Your previous response was empty. Please provide a helpful response."


def create_plugin(ctx):
    """Empty retry plugin"""
    cmd = EmptyRetryCommand(ctx.app)

    # Register commands
    ctx.register_command("/r", lambda args: cmd.handle_r(args))
    ctx.register_command("/empty-retry", lambda args: cmd.handle_empty_retry(args))

    # Register hook for auto-detection
    ctx.register_hook("after_ai_processing", cmd.handle_hook)

    if Config.debug():
        LogUtils.print("[+] Empty retry plugin loaded")
        LogUtils.print("    - /r command (manual retry)")
        LogUtils.print("    - /empty-retry command (settings)")

    return {}
