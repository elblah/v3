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
- /auto-next-prompt task-complete on   - Allow AI to stop loop (default)
- /auto-next-prompt task-complete off  - Force AI to always produce next action
- /auto-next-prompt history         - Show prompt history with timings
- /auto-next-prompt help            - Show usage

Env vars:
- AUTO_NEXT_CLEAN_SLATE=1     (default: 1) wipe history before prompt
- AUTO_NEXT_TASK_COMPLETE=1   (default: 1) allow AI to stop via TASK_COMPLETE
- AUTO_NEXT_MAX_ATTEMPTS=N    (default: 2)

Hook: after_ai_processing - returns next prompt or continuation request
"""

import json
import os
import re
import time
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


def _build_inject_message(goal: str, task_complete: bool = True) -> str:
    """Build injection message, optionally with drift guard.
    When task_complete is False, strips TASK_COMPLETE references."""
    msg = _INJECT_BASE
    if goal:
        msg += _DRIFT_GUARD.format(g=goal)
    if not task_complete:
        msg = re.sub(r'<prompt>TASK_COMPLETE</prompt>', '<prompt>your next action here</prompt>', msg)
        msg = re.sub(r'(?m)^- .*TASK_COMPLETE.*\n?', '', msg)
        msg += "\nIMPORTANT: There is NO escape hatch. You MUST generate a meaningful next action that advances the project. Never suggest waiting for user input."
    return msg


# Static state
_enabled = False
_awaiting_tag = False
_attempts = 0
_goal = ""
_prompt_history = []  # list of {"prompt": str, "started_at": float, "ended_at": float|None}
_clean_slate = os.environ.get("AUTO_NEXT_CLEAN_SLATE", "1") == "1"
_task_complete = os.environ.get("AUTO_NEXT_TASK_COMPLETE", "1") == "1"
_max_attempts = int(os.environ.get("AUTO_NEXT_MAX_ATTEMPTS", "2"))

_STATE_FILE = os.path.join(os.getcwd(), ".aicoder", "auto-next-prompt.json")


def _load_state() -> None:
    """Load persisted goal, clean_slate, task_complete from disk"""
    global _goal, _clean_slate, _task_complete
    try:
        with open(_STATE_FILE) as f:
            data = json.load(f)
        if "goal" in data:
            _goal = data["goal"]
        if "clean_slate" in data:
            _clean_slate = data["clean_slate"]
        if "task_complete" in data:
            _task_complete = data["task_complete"]
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def _save_state() -> None:
    """Persist goal, clean_slate, task_complete to disk"""
    global _goal, _clean_slate, _task_complete
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    try:
        with open(_STATE_FILE, "w") as f:
            json.dump({"goal": _goal, "clean_slate": _clean_slate, "task_complete": _task_complete}, f)
    except OSError:
        pass


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

    global _enabled, _awaiting_tag, _attempts, _goal, _clean_slate, _task_complete

    _load_state()

    app = ctx.app

    def _get_messages():
        return app.message_history.messages

    def _status() -> str:
        """Build multi-line status display"""
        c = Config.colors
        lines = [
            f"{c['bold']}Auto-next-prompt{c['reset']}",
            f"  State:          {'ON' if _enabled else 'OFF'}{' (waiting for <prompt>, ' + str(_attempts) + '/' + str(_max_attempts) + ')' if _awaiting_tag else ''}",
            f"  Goal:           {_goal if _goal else c['dim'] + '(none)' + c['reset']}",
            f"  Clean-slate:    {'ON' if _clean_slate else 'OFF'}",
            f"  Task-complete:  {'ON' if _task_complete else 'OFF'}",
        ]
        return "\n".join(lines)

    def _handle_command(args_str: str) -> str:
        global _enabled, _awaiting_tag, _attempts, _goal, _clean_slate, _task_complete

        args = args_str.strip()

        if args.lower() == "on":
            _enabled = True
            _awaiting_tag = False
            _attempts = 0
            return _status()

        if args.lower() == "off":
            _enabled = False
            _awaiting_tag = False
            _attempts = 0
            return "Auto-next-prompt disabled."

        if args.lower() in ("help", "?"):
            return (
                "Auto-next-prompt subcommands:\n"
                "  on               - enable auto-continuation\n"
                "  off              - disable\n"
                "  goal <text>      - set task goal (drift guard)\n"
                "  goal off         - clear goal\n"
                "  clean-slate on   - wipe history before each prompt\n"
                "  clean-slate off  - keep history (default)\n"
                "  task-complete on - disable auto-next on TASK_COMPLETE (default)\n"
                "  task-complete off- ignore TASK_COMPLETE, keep looping\n"
                "  history          - show prompt history with timings\n"
                "  help             - this message"
            )

        if args.lower().startswith("goal"):
            rest = args[4:].strip()
            if rest.lower() in ("off", "clear", ""):
                _goal = ""
                _save_state()
                return "Goal cleared."
            _goal = rest
            _save_state()
            return f"Goal set: {_goal}"

        if args.lower().startswith("clean-slate"):
            rest = args[11:].strip().lower()
            if rest == "on":
                _clean_slate = True
                _save_state()
                return "Clean-slate: ON (history wiped before each prompt)"
            if rest == "off":
                _clean_slate = False
                _save_state()
                return "Clean-slate: OFF"
            return f"Clean-slate: {'ON' if _clean_slate else 'OFF'}"

        if args.lower().startswith("task-complete"):
            rest = args[13:].strip().lower()
            if rest == "on":
                _task_complete = True
                _save_state()
                return "Task-complete: ON (auto-disable on TASK_COMPLETE)"
            if rest == "off":
                _task_complete = False
                _save_state()
                return "Task-complete: OFF (ignore TASK_COMPLETE, keep looping)"
            return f"Task-complete: {'ON' if _task_complete else 'OFF'}"

        if args.lower() in ("history", "last-prompt"):
            if not _prompt_history:
                return "No prompts in history."
            c = Config.colors
            lines = []
            now = time.time()
            for i, entry in enumerate(_prompt_history, 1):
                prompt = entry["prompt"]
                elapsed = now - entry["started_at"]
                if entry["ended_at"] is not None:
                    duration = entry["ended_at"] - entry["started_at"]
                    status = f"took {duration/60:.1f} min"
                else:
                    status = f"ongoing for {elapsed/60:.1f} min"
                lines.append(f"{c['bold']}{i}{c['reset']} - {c['dim']}{status}{c['reset']}")
                lines.append(f"    {prompt}")
                lines.append("")
            return "\n".join(lines).rstrip()

        # Show status (multi-line)
        return _status()

    def _on_after_ai_processing(has_tool_calls) -> Optional[str]:
        global _enabled, _awaiting_tag, _attempts, _goal, _clean_slate, _prompt_history, _task_complete
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
                if _task_complete:
                    _enabled = False
                    # Close previous timing
                    if _prompt_history and _prompt_history[-1]["ended_at"] is None:
                        _prompt_history[-1]["ended_at"] = time.time()
                    _prompt_history.append({"prompt": prompt, "started_at": time.time(), "ended_at": None})
                    LogUtils.print()
                    LogUtils.print(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} {c['green']}task complete - auto-next-prompt disabled{c['reset']}")
                    return None
                else:
                    # TASK_COMPLETE disabled — reject it, force AI to try again
                    _awaiting_tag = True
                    _attempts = 1
                    LogUtils.print(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} {c['yellow']}TASK_COMPLETE rejected (disabled) — forcing next action...{c['reset']}")
                    return _build_inject_message(_goal, _task_complete)

            # Close previous prompt timing
            if _prompt_history and _prompt_history[-1]["ended_at"] is None:
                _prompt_history[-1]["ended_at"] = time.time()
            # Record new prompt
            _prompt_history.append({"prompt": prompt, "started_at": time.time(), "ended_at": None})

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
            return _build_inject_message(_goal, _task_complete)

        # First completion - inject continuation request
        _awaiting_tag = True
        _attempts = 1
        LogUtils.print(f"{c['brightMagenta']}[auto-next-prompt]{c['reset']} asking for next action...")
        return _build_inject_message(_goal, _task_complete)

    def _on_context_bar() -> Optional[str]:
        """Append prompt count + elapsed time to context bar"""
        if not _enabled or not _prompt_history:
            return None
        idx = len(_prompt_history)
        last = _prompt_history[-1]
        elapsed = (time.time() - last["started_at"]) / 60
        return f"auto#{idx} ({elapsed:.1f}min)"

    # Register hooks
    ctx.register_hook("after_ai_processing", _on_after_ai_processing)
    ctx.register_hook("on_context_bar", _on_context_bar)

    # Register command
    ctx.register_command("auto-next-prompt", _handle_command, description="Auto-generate next prompts based on goal")

    if Config.debug():
        LogUtils.print("[+] auto-next-prompt plugin loaded")

    return {}