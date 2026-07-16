"""
Auto-Next-Prompt Plugin - Automatically suggest next actions

Monitors AI completion and generates continuation prompts.

Commands:
- /auto-next-prompt on              - Enable auto-continuation
- /auto-next-prompt off             - Disable
- /auto-next-prompt                 - Show status
- /auto-next-prompt goal ...        - Set/clear goal for drift guard
- /auto-next-prompt clean-slate on  - Wipe history before each prompt
- /auto-next-prompt clean-slate off - Keep history (default)
- /auto-next-prompt help            - Show usage

Env vars:
- AUTO_NEXT_CLEAN_SLATE=1  (default: 1) wipe history before prompt
- AUTO_NEXT_MAX_ATTEMPTS=N (default: 2)

Hook: after_ai_processing - returns next prompt or continuation request
"""

import os
import re
from typing import Optional

from aicoder.utils.log import LogUtils
from aicoder.core.config import Config


# Base injection template (customizable via NEXT_PROMPT_CUSTOM env var)
_INJECT_BASE = os.environ.get(
    "NEXT_PROMPT_CUSTOM",
    """Examine the conversation context. Use tools to read files, search code, etc. if needed. Then determine the next logical action.

IMPORTANT: Your role is to decide what to do next. You CAN use tools (read_file, run_shell_command, etc.) freely to explore the codebase and understand state before committing to an action.

When ready, output:
<prompt>Your next action here</prompt>

Guidelines:
- The <prompt> is your committed next step. Use tools FIRST to explore, THEN output <prompt>.
- Focus on CONCRETE ACTIONS the AI can take NOW
- DO NOT suggest waiting for user input
- If no clear next step exists, use <prompt>TASK_COMPLETE</prompt>
"""
)

_DRIFT_GUARD = """
CRITICAL: The user's current task is:
{g}

Your <prompt> MUST directly advance THIS task. Do NOT suggest unrelated infrastructure, test harnesses, refactors, or tangents from memory files. If the task is complete, use <prompt>TASK_COMPLETE</prompt>.
"""


def _extract_prompt_tag(text: str) -> Optional[str]:
    """Extract content from <prompt>...</prompt> tags"""
    if not text:
        return None
    match = re.search(r'<prompt>(.*?)</prompt>', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _build_inject_message(goal: str) -> str:
    """Build injection message, optionally with drift guard"""
    if goal:
        return _INJECT_BASE + _DRIFT_GUARD.format(g=goal)
    return _INJECT_BASE


# Static state
_enabled = False
_awaiting_tag = False
_attempts = 0
_goal = ""
_clean_slate = os.environ.get("AUTO_NEXT_CLEAN_SLATE", "1") == "1"
_max_attempts = int(os.environ.get("AUTO_NEXT_MAX_ATTEMPTS", "2"))


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

    global _enabled, _awaiting_tag, _attempts, _goal, _clean_slate

    app = ctx.app

    def _get_messages():
        return app.message_history.messages

    def _handle_command(args_str: str) -> str:
        global _enabled, _awaiting_tag, _attempts, _goal, _clean_slate

        args = args_str.strip()

        if args.lower() == "on":
            _enabled = True
            _awaiting_tag = False
            _attempts = 0
            return "Auto-next-prompt enabled."

        if args.lower() == "off":
            _enabled = False
            _awaiting_tag = False
            _attempts = 0
            return "Auto-next-prompt disabled."

        if args.lower() in ("help", "?"):
            return (
                "Auto-next-prompt subcommands:\n"
                "  on              - enable auto-continuation\n"
                "  off             - disable\n"
                "  goal <text>     - set task goal (drift guard)\n"
                "  goal off        - clear goal\n"
                "  clean-slate on  - wipe history before next prompt\n"
                "  clean-slate off - keep history (default)\n"
                "  help            - this message"
            )

        if args.lower().startswith("goal"):
            rest = args[4:].strip()
            if rest.lower() in ("off", "clear", ""):
                _goal = ""
                return "Goal cleared."
            _goal = rest
            return f"Goal set: {_goal}"

        if args.lower().startswith("clean-slate"):
            rest = args[11:].strip().lower()
            if rest == "on":
                _clean_slate = True
                return "Clean-slate: ON (history wiped before each prompt)"
            if rest == "off":
                _clean_slate = False
                return "Clean-slate: OFF"
            return f"Clean-slate: {'ON' if _clean_slate else 'OFF'}"

        # Show status
        parts = []
        if _enabled:
            parts.append("enabled")
            if _awaiting_tag:
                parts.append(f"(waiting for <prompt>, {_attempts}/{_max_attempts})")
        else:
            parts.append("disabled")
        if _goal:
            parts.append(f"| goal: {_goal}")
        parts.append(f"| clean-slate: {'ON' if _clean_slate else 'OFF'}")
        return "Auto-next-prompt: " + " ".join(parts)

    def _on_after_ai_processing(has_tool_calls) -> Optional[str]:
        global _enabled, _awaiting_tag, _attempts, _goal, _clean_slate
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
            _awaiting_tag = False
            _attempts = 0

            if prompt.upper() == "TASK_COMPLETE":
                _enabled = False
                LogUtils.print()
                LogUtils.print(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} {c['green']}task complete - auto-next-prompt disabled{c['reset']}")
                return None

            if _clean_slate:
                app.message_history.clear()
                LogUtils.print(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} {c['dim']}history wiped (clean-slate){c['reset']}")
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
                LogUtils.warn(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} giving up (no <prompt> tag after {_max_attempts} attempts)")

            # Ask again
            LogUtils.print(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} AI didn't provide <prompt> tag, asking again...")
            return _build_inject_message(_goal)

        # First completion - inject continuation request
        _awaiting_tag = True
        _attempts = 1
        LogUtils.print(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} asking for next action...")
        return _build_inject_message(_goal)

    # Register hooks
    ctx.register_hook("after_ai_processing", _on_after_ai_processing)

    # Register command
    ctx.register_command("auto-next-prompt", _handle_command, description="Auto-generate next prompts based on goal")

    if Config.debug():
        LogUtils.print("[+] auto-next-prompt plugin loaded")

    return {}