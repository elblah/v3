"""
Auto-Next-Prompt Plugin - Automatically suggest and execute next actions

Monitors AI completion and generates continuation prompts based on goal.
Requires goal to be set (via /goal or [GOAL] message).

Commands:
- /auto-next-prompt on    - Enable auto-continuation
- /auto-next-prompt off   - Disable
- /auto-next-prompt       - Show status

Hook: after_ai_processing - returns next prompt or continuation request
"""

import re
from typing import Optional

from aicoder.utils.log import LogUtils
from aicoder.core.config import Config


# Injection message template
INJECT_MESSAGE = """Based on the goal and the work we just completed, generate the next logical action to continue progress.

Format your response as:
<prompt>Your next action here</prompt>

Guidelines:
- Focus on CONCRETE ACTIONS the AI can take NOW (write code, run tests, create files, etc.)
- DO NOT suggest waiting for user input - if the task requires user input, suggest something else the AI can do
- If implementation is done, suggest testing, documentation, or review
- Consider dependencies: tests after code, docs after features
- Keep it to one clear, actionable step
- Suggest something that advances the goal, not something passive

Current goal: {goal}
"""


def _get_goal_from_messages(messages: list) -> Optional[str]:
    """Extract goal from [GOAL] message in conversation"""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and content.startswith("[GOAL]"):
                prefix = "[GOAL] Session goal: "
                if content.startswith(prefix):
                    return content[len(prefix):].strip()
    return None


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
            goal = _get_goal_from_messages(_get_messages())
            if not goal:
                return "No goal set. Use /goal <text> first, then enable auto-next-prompt."

            _enabled = True
            _awaiting_tag = False
            _attempts = 0
            return f"Auto-next-prompt enabled. Goal: {goal}"

        if args == "off":
            _enabled = False
            _awaiting_tag = False
            _attempts = 0
            return "Auto-next-prompt disabled."

        # Show status
        goal = _get_goal_from_messages(_get_messages())
        if not goal:
            return "Auto-next-prompt: disabled (no goal set)"
        if _enabled:
            if _awaiting_tag:
                return f"Auto-next-prompt: enabled (waiting for <prompt> tag, {_attempts}/{_max_attempts}). Goal: {goal}"
            return f"Auto-next-prompt: enabled. Goal: {goal}"
        return f"Auto-next-prompt: disabled. Goal: {goal}"

    def _on_after_ai_processing(has_tool_calls) -> Optional[str]:
        global _enabled, _awaiting_tag, _attempts

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
            LogUtils.print(f"[auto-next-prompt] Next action: {prompt[:60]}{'...' if len(prompt) > 60 else ''}")
            return prompt

        # No tag found
        goal = _get_goal_from_messages(messages)
        if not goal:
            _enabled = False
            LogUtils.warn("[!] Auto-next-prompt: no goal found, disabling")
            return None

        if _awaiting_tag:
            # Already asked, AI didn't give tag
            _attempts += 1
            if _attempts >= _max_attempts:
                _enabled = False
                _awaiting_tag = False
                _attempts = 0
                LogUtils.warn("[!] Auto-next-prompt: giving up (no <prompt> tag after 2 attempts)")
                return None

            # Ask again
            LogUtils.print("[auto-next-prompt] AI didn't provide <prompt> tag, asking again...")
            return INJECT_MESSAGE.format(goal=goal)

        # First completion - inject continuation request
        _awaiting_tag = True
        _attempts = 1
        LogUtils.print("[auto-next-prompt] Asking AI for next action...")
        return INJECT_MESSAGE.format(goal=goal)

    # Register hooks
    ctx.register_hook("after_ai_processing", _on_after_ai_processing)

    # Register command
    ctx.register_command("auto-next-prompt", _handle_command, description="Auto-generate next prompts based on goal")

    if Config.debug():
        LogUtils.print("[+] auto-next-prompt plugin loaded")

    return {}