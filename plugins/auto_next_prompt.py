"""
Auto-Next-Prompt Plugin - Automatically suggest next actions

Monitors AI completion and generates continuation prompts.
Works with or without goal plugin - goal is considered via conversation context.

Commands:
- /auto-next-prompt on    - Enable auto-continuation
- /auto-next-prompt off   - Disable
- /auto-next-prompt       - Show status

Hook: after_ai_processing - returns next prompt or continuation request
"""

import os
import re
from typing import Optional

from aicoder.utils.log import LogUtils
from aicoder.core.config import Config


# Injection message template (customizable via NEXT_PROMPT_CUSTOM env var)
INJECT_MESSAGE = os.environ.get(
    "NEXT_PROMPT_CUSTOM",
    """Based on the work we just completed, generate the next logical action to continue progress.

Format your response as:
<prompt>Your next action here</prompt>

Guidelines:
- Focus on CONCRETE ACTIONS the AI can take NOW
- DO NOT suggest waiting for user input - suggest something else instead
- Keep it to one clear, actionable step
- Use good taste when choosing the next action
"""
)


def _extract_prompt_tag(text: str) -> Optional[str]:
    """Extract content from <prompt>...</prompt> tags"""
    if not text:
        return None
    match = re.search(r'<prompt>(.*?)</prompt>', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


# Static state
_enabled = False
_awaiting_tag = False
_attempts = 0
_max_attempts = 2


def _get_last_response(messages: list) -> str:
    """Get the last AI response content"""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        return item.get("text", "")
    return ""


def create_plugin(ctx):
    """Create auto-next-prompt plugin"""

    global _enabled, _awaiting_tag, _attempts

    app = ctx.app

    def _get_messages():
        return app.message_history.messages

    def _handle_command(args_str: str) -> str:
        global _enabled, _awaiting_tag, _attempts

        args = args_str.strip().lower()

        if args == "on":
            _enabled = True
            _awaiting_tag = False
            _attempts = 0
            return "Auto-next-prompt enabled."

        if args == "off":
            _enabled = False
            _awaiting_tag = False
            _attempts = 0
            return "Auto-next-prompt disabled."

        # Show status
        if _enabled:
            if _awaiting_tag:
                return f"Auto-next-prompt: enabled (waiting for <prompt> tag, {_attempts}/{_max_attempts})"
            return "Auto-next-prompt: enabled"
        return "Auto-next-prompt: disabled"

    def _on_after_ai_processing(has_tool_calls) -> Optional[str]:
        global _enabled, _awaiting_tag, _attempts
        c = Config.colors

        if not _enabled:
            return None

        # Skip if AI did tool calls (still working)
        if has_tool_calls:
            return None

        messages = _get_messages()
        response = _get_last_response(messages)

        # Check for prompt tag
        prompt = _extract_prompt_tag(response)

        if prompt:
            # Found it - use this as next prompt
            _awaiting_tag = False
            _attempts = 0
            LogUtils.print()  # separator
            LogUtils.print(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} {c['brightCyan']}Next action:{c['reset']} {prompt}")
            return prompt

        # No tag found - inject continuation request
        if _awaiting_tag:
            # Already asked, AI didn't give tag
            _attempts += 1
            if _attempts >= _max_attempts:
                _enabled = False
                _awaiting_tag = False
                _attempts = 0
                LogUtils.warn(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} giving up (no <prompt> tag after 2 attempts)")

            # Ask again
            LogUtils.print(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} AI didn't provide <prompt> tag, asking again...")
            return INJECT_MESSAGE

        # First completion - inject continuation request
        _awaiting_tag = True
        _attempts = 1
        LogUtils.print(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} asking for next action...")
        return INJECT_MESSAGE

    # Register hooks
    ctx.register_hook("after_ai_processing", _on_after_ai_processing)

    # Register command
    ctx.register_command("auto-next-prompt", _handle_command, description="Auto-generate next prompts based on goal")

    if Config.debug():
        LogUtils.print("[+] auto-next-prompt plugin loaded")

    return {}