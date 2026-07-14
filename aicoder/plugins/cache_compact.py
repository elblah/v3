"""
cache_compact.py - Cache-aware compaction

Three injection paths:
- Passive: system-prompt nudge for voluntary [COMPACT_SUMMARY] at natural breakpoints.
- User turn: after_user_prompt appends <system-reminder> to user's input.
- Autonomous: after_ai_processing injects instruction into history when AI is
  in a tool-calling loop (no user input between turns).

Compaction fires on after_assistant_message_added:
- [COMPACT_SUMMARY] tag detected -> compact (existing path)
- No tag -> fail, let after_ai_processing re-inject next turn

Tier boundaries (coexists with existing tiers):
- [CACHE_COMPACT_THRESHOLD, CACHE_COMPACT_DEFER) -> this plugin
- [80%, 95%)  -> compact_strategy plugin (forced, untouched)
- [95%, 100%] -> core auto-compact (brutal, untouched)

Env:
- CACHE_COMPACT_THRESHOLD  trigger % of context size (default 50, 0 = disabled)
- CACHE_COMPACT_DEFER      upper bound % to defer to existing tiers (default 80)
- CACHE_COMPACT_MAXFAILS   consecutive failures before standing down (default 3)
- CACHE_COMPACT_FORCE=1    use ultra-forceful instruction (default: forceful)
- CACHE_COMPACT_KEEP_PERCENT  keep N% of recent context after [SUMMARY] (default 0 = brutal)
- CACHE_COMPACT_DEBUG=1    verbose log: per-msg fail count & suggestion events
"""

import os
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

import re

SUMMARY_TAG = "[SUMMARY]"
COMPACT_TAG = "[COMPACT_SUMMARY]"

PASSIVE_INSTRUCTION = """If you're at a natural breakpoint and the conversation feels long, you may optionally begin your response with `[COMPACT_SUMMARY]`. If you do, follow with a summary of task, progress, decisions, files, next steps. This replaces everything else in context with just that summary. Use rarely — only when genuinely helpful to save space."""

# Detect [COMPACT_SUMMARY] even if dumb AIs wrap it in markdown formatting
_RE_COMPACT_TAG_LEADING = re.compile(r"^[*_`#\s]*(\[COMPACT_SUMMARY\])")
_RE_SYSTEM_REMINDER = re.compile(r"\n\n<system-reminder>.*?</system-reminder>", re.DOTALL)

# Signature substring in injected compaction instructions. Used to filter
# autonomous-path messages from recent window during compaction.
_COMPACT_SIGNATURE = "COMPACTION REQUIRED"

COMPACT_INSTRUCTION = (
    "SYSTEM: Context too large. COMPACTION REQUIRED.\n"
    "Produce a self-contained summary of the entire conversation above.\n"
    "Begin with [COMPACT_SUMMARY]. Do NOT call any tools. Do NOT continue working.\n"
    "Include: task, progress, key decisions with rationale, file paths and line numbers, "
    "current state, failed approaches, next steps.\n"
    "This summary becomes your ENTIRE memory — omit nothing critical."
)

FORCE_COMPACT_INSTRUCTION = (
    "⚠ SYSTEM REQUEST — NOT OPTIONAL. COMPACTION REQUIRED NOW. ⚠\n"
    "Context limit approaching. You MUST comply:\n"
    "1. Do NOT call any tools\n"
    "2. Begin response with [COMPACT_SUMMARY]\n"
    "3. Write a self-contained summary of the ENTIRE conversation above\n"
    "4. Include: task, progress, key decisions with rationale, file paths and line numbers, "
    "current state, failed approaches, next steps\n"
    "5. This summary becomes your ENTIRE memory — omit nothing critical\n\n"
    "OUTPUT ONLY THE SUMMARY. DO NOT CONTINUE WORKING. COMPLY NOW."
)


def _content_str(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text", "")
    return ""


def _is_summary_first_printable(text: str) -> bool:
    """True if [COMPACT_SUMMARY] is the first printable content (ignoring leading whitespace/markdown)."""
    if COMPACT_TAG not in text:
        return False
    return bool(_RE_COMPACT_TAG_LEADING.match(text))


def _select_recent_by_percent(messages, keep_percent, max_tokens):
    """Select recent messages by token percentage. Keeps complete rounds."""
    if keep_percent <= 0 or not messages:
        return []

    target_tokens = int(max_tokens * (keep_percent / 100))
    from aicoder.core.token_estimator import _message_cache

    selected = []  # (msg, tokens) pairs
    kept_tokens = 0
    for msg in reversed(messages):
        if msg.get("role") == "system":
            continue
        tokens = _message_cache.get(id(msg), 0)
        if selected and kept_tokens + tokens > target_tokens:
            break
        selected.insert(0, (msg, tokens))
        kept_tokens += tokens

    # Trim orphaned tool responses at start (no preceding assistant with tool_calls)
    while selected and selected[0][0].get("role") == "tool":
        selected.pop(0)

    # Build copies with system-reminders stripped from user messages
    result = []
    for msg, _ in selected:
        m = dict(msg)
        if m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                m["content"] = _RE_SYSTEM_REMINDER.sub("", content)
        result.append(m)
    return result


def _compact(messages, app, state, keep_percent=0):
    """Replace history with [system, summary, ...recent], reset state."""
    system_msg = messages[0] if messages[0].get("role") == "system" else None
    # If there's already a [SUMMARY] user message, keep it as-is
    last = messages[-1]
    summary_content = _content_str(last.get("content", ""))
    # Normalize: strip leading markdown/whitespace, convert [COMPACT_SUMMARY] → [SUMMARY]
    # so prune_old_summaries can find it on subsequent compactions
    m = _RE_COMPACT_TAG_LEADING.match(summary_content)
    if m:
        summary_content = SUMMARY_TAG + summary_content[m.end(1):]
    else:
        summary_content = f"{SUMMARY_TAG} {summary_content}"
    summary_msg = {"role": "user", "content": summary_content}
    recent = []
    if keep_percent > 0 and len(messages) > 2:
        candidates = [
            m for m in messages[1:-1]
            if not (m.get("role") == "user"
                    and isinstance(m.get("content"), str)
                    and _COMPACT_SIGNATURE in m["content"])
        ]
        recent = _select_recent_by_percent(
            candidates, keep_percent, Config.context_size()
        )
    new_msgs = ([system_msg, summary_msg] if system_msg else [summary_msg]) + recent
    before = len(messages)
    app.message_history.set_messages(new_msgs)
    app.message_history.prune_old_summaries()
    app.message_history.increment_compaction_count()
    state["awaiting"] = False
    state["fails"] = 0
    app.set_next_prompt(
        "Context compacted above. Continue working if you have an unfinished task."
    )
    c = Config.colors
    keep_info = f", kept {len(recent)} recent" if recent else ""
    LogUtils.print(
        f"\n\n{c['bold']}{c['green']}[cache_compact] accepted [COMPACT_SUMMARY] "
        f"-> {before} to {len(new_msgs)} msgs{keep_info}{c['reset']}\n"
    )


def _compact_keep_assistant(app, state, assistant_msg, keep_percent=0):
    """Compact old messages but keep the assistant message (with tool_calls) intact."""
    messages = app.message_history.get_messages()
    system_msg = (
        messages[0] if messages and messages[0].get("role") == "system" else None
    )
    recent = []
    if keep_percent > 0 and len(messages) > 2:
        # Messages between system and the assistant summary
        idx = -1
        for i, m in enumerate(messages):
            if m is assistant_msg:
                idx = i
                break
        if idx > 1:
            candidates = [
                m for m in messages[1:idx]
                if not (m.get("role") == "user"
                        and isinstance(m.get("content"), str)
                        and _COMPACT_SIGNATURE in m["content"])
            ]
            recent = _select_recent_by_percent(
                candidates, keep_percent, Config.context_size()
            )
    prefix = [system_msg] if system_msg else []
    # Normalize assistant message: [COMPACT_SUMMARY] → [SUMMARY] for internal storage
    normalized = dict(assistant_msg)
    raw = _content_str(normalized.get("content", ""))
    m = _RE_COMPACT_TAG_LEADING.match(raw)
    if m:
        normalized["content"] = SUMMARY_TAG + raw[m.end(1):]
    new_msgs = prefix + recent + [normalized]
    before = len(messages)
    app.message_history.set_messages(new_msgs)
    app.message_history.prune_old_summaries()
    app.message_history.increment_compaction_count()
    state["awaiting"] = False
    state["fails"] = 0
    app.set_next_prompt(
        "Context compacted above. Continue working if you have an unfinished task."
    )
    c = Config.colors
    keep_info = f", kept {len(recent)} recent" if recent else ""
    LogUtils.print(
        f"\n\n{c['bold']}{c['green']}[cache_compact] accepted [COMPACT_SUMMARY] (with tool_calls) "
        f"-> {before} to {len(new_msgs)} msgs{keep_info}{c['reset']}\n"
    )


def create_plugin(ctx):
    app = ctx.app

    cfg = {
        "threshold": int(os.environ.get("CACHE_COMPACT_THRESHOLD", "50")),
        "defer": int(os.environ.get("CACHE_COMPACT_DEFER", "80")),
        "max_fails": int(os.environ.get("CACHE_COMPACT_MAXFAILS", "3")),
        "force": os.environ.get("CACHE_COMPACT_FORCE", "").lower()
        in ("1", "true", "yes"),
        "keep_percent": int(os.environ.get("CACHE_COMPACT_KEEP_PERCENT", "0")),
    }

    state = {"awaiting": False, "fails": 0}

    def _on_system_prompt_append():
        if cfg["threshold"] > 0:
            return PASSIVE_INSTRUCTION
        return None

    def _on_assistant_message_added(message):
        """after_assistant_message_added hook - detect [COMPACT_SUMMARY] tag."""
        if cfg["threshold"] <= 0:
            return
        content = _content_str(message.get("content", ""))
        is_summary = content and _is_summary_first_printable(content)
        if is_summary:
            if message.get("tool_calls"):
                _compact_keep_assistant(app, state, message, cfg["keep_percent"])
            else:
                _compact(app.message_history.get_messages(), app, state, cfg["keep_percent"])
        elif state["awaiting"]:
            if message.get("tool_calls"):
                # AI ignored instruction, kept making tool calls
                state["awaiting"] = False
                state["fails"] += 1
                if os.environ.get("CACHE_COMPACT_DEBUG"):
                    c = Config.colors
                    LogUtils.print(
                        f"{c['yellow']}[cache_compact] AI ignored compaction request "
                        f"({state['fails']}/{cfg['max_fails']}){c['reset']}"
                    )
            else:
                # AI produced text without [COMPACT_SUMMARY] tag — count as fail
                state["awaiting"] = False
                state["fails"] += 1
                if os.environ.get("CACHE_COMPACT_DEBUG"):
                    c = Config.colors
                    LogUtils.print(
                        f"{c['yellow']}[cache_compact] no [COMPACT_SUMMARY] tag "
                        f"({state['fails']}/{cfg['max_fails']}){c['reset']}"
                    )

    def _on_after_ai_processing(has_tool_calls=None):
        """after_ai_processing hook - inject compaction request for autonomous loops."""
        if cfg["threshold"] <= 0:
            return

        # Handle stale awaiting (e.g. empty response skipped after_assistant_message_added)
        if state["awaiting"]:
            state["awaiting"] = False
            state["fails"] += 1
            if os.environ.get("CACHE_COMPACT_DEBUG"):
                c = Config.colors
                LogUtils.print(
                    f"{c['yellow']}[cache_compact] no [COMPACT_SUMMARY] received "
                    f"({state['fails']}/{cfg['max_fails']}){c['reset']}"
                )

        current = app.stats.current_prompt_size or 0
        max_size = Config.context_size()
        pct = (current / max_size * 100) if max_size else 0

        if pct < cfg["threshold"]:
            state["fails"] = 0
            return
        if pct >= cfg["defer"]:
            return
        if state["fails"] >= cfg["max_fails"]:
            return

        if not has_tool_calls:
            return  # User turn — after_user_prompt handles injection

        # Autonomous loop: inject instruction directly into history.
        # Tool results are already in history; next process_with_ai() is automatic.
        instruction = FORCE_COMPACT_INSTRUCTION if cfg["force"] else COMPACT_INSTRUCTION
        app.message_history.add_user_message(
            f"<system-reminder>\n{instruction}\n</system-reminder>"
        )
        state["awaiting"] = True
        if os.environ.get("CACHE_COMPACT_DEBUG"):
            c = Config.colors
            LogUtils.print(
                f"{c['bold']}{c['cyan']}[cache_compact] {pct:.0f}% context "
                f"-> injected compaction request (autonomous){c['reset']}"
            )

    def _suggest_compaction(user_input: str) -> str:
        """after_user_prompt hook - inject <system-reminder> if context growing."""
        if cfg["threshold"] <= 0:
            return user_input

        messages = app.message_history.get_messages()
        if not messages:
            return user_input

        if state["awaiting"]:
            state["awaiting"] = False
            state["fails"] += 1
            if os.environ.get("CACHE_COMPACT_DEBUG"):
                c = Config.colors
                LogUtils.print(
                    f"{c['yellow']}[cache_compact] no [COMPACT_SUMMARY] received "
                    f"({state['fails']}/{cfg['max_fails']}){c['reset']}"
                )

        current = app.stats.current_prompt_size or 0
        max_size = Config.context_size()
        pct = (current / max_size * 100) if max_size else 0

        if pct < cfg["threshold"]:
            state["fails"] = 0
            return user_input
        if pct >= cfg["defer"]:
            return user_input
        if state["fails"] >= cfg["max_fails"]:
            return user_input

        if user_input.startswith("/"):
            return user_input

        instruction = FORCE_COMPACT_INSTRUCTION if cfg["force"] else COMPACT_INSTRUCTION
        state["awaiting"] = True
        if os.environ.get("CACHE_COMPACT_DEBUG"):
            c = Config.colors
            LogUtils.print(
                f"{c['bold']}{c['cyan']}[cache_compact] {pct:.0f}% context "
                f"-> appended compaction request{c['reset']}"
            )
        return f"{user_input}\n\n<system-reminder>\n{instruction}\n</system-reminder>"

    ctx.register_hook("on_system_prompt_append", _on_system_prompt_append)
    ctx.register_hook("after_assistant_message_added", _on_assistant_message_added)
    ctx.register_hook("after_ai_processing", _on_after_ai_processing)
    ctx.register_hook("after_user_prompt", _suggest_compaction)

    def _on_info(sub: str) -> None:
        if sub == "config":
            c = Config.colors
            status = "awaiting" if state["awaiting"] else "idle"
            enabled = cfg["threshold"] > 0
            print(
                f"{c['bold']}cache_compact:{c['reset']} {'enabled' if enabled else 'disabled'}"
            )
            if enabled:
                mode = "force" if cfg["force"] else "soft"
                print(
                    f"  threshold: {cfg['threshold']}%  defer: {cfg['defer']}%  maxfails: {cfg['max_fails']}  keep: {cfg['keep_percent']}%"
                )
                print(f"  mode: {mode}  state: {status}  fails: {state['fails']}")

    ctx.register_hook("on_info", _on_info)

    def _handle_cc(args_str):
        """Handle /cache-compact command"""
        parts = args_str.strip().split()
        sub = parts[0] if parts else "status"

        if sub == "status" or sub == "":
            enabled = cfg["threshold"] > 0
            c = Config.colors
            status = "awaiting" if state["awaiting"] else "idle"
            mode = "force" if cfg["force"] else "soft"
            print(
                f"{c['bold']}cache_compact:{c['reset']} {'enabled' if enabled else 'disabled'}"
            )
            if enabled:
                print(
                    f"  threshold: {cfg['threshold']}%  defer: {cfg['defer']}%  maxfails: {cfg['max_fails']}  keep: {cfg['keep_percent']}%"
                )
                print(f"  mode: {mode}  state: {status}  fails: {state['fails']}")
            else:
                print(
                    f"  threshold: 0 (disabled)  defer: {cfg['defer']}%  maxfails: {cfg['max_fails']}  keep: {cfg['keep_percent']}%"
                )

        elif sub == "enable":
            val = int(parts[1]) if len(parts) > 1 else 50
            if val <= 0:
                print("threshold must be > 0")
                return
            cfg["threshold"] = val
            LogUtils.print(f"[cache_compact] enabled (threshold={val}%)")

        elif sub == "disable":
            cfg["threshold"] = 0
            LogUtils.print("[cache_compact] disabled")

        elif sub == "set":
            if len(parts) < 3:
                print("usage: /cache-compact set <key> <value>")
                print("  keys: threshold, defer, maxfails, force, keep, debug")
                return
            key = parts[1]
            val = parts[2]
            if key == "threshold":
                cfg["threshold"] = int(val)
            elif key == "defer":
                cfg["defer"] = int(val)
            elif key == "maxfails":
                cfg["max_fails"] = int(val)
            elif key == "force":
                cfg["force"] = val.lower() in ("1", "true", "yes")
            elif key == "keep":
                cfg["keep_percent"] = int(val)
            elif key == "debug":
                os.environ["CACHE_COMPACT_DEBUG"] = val if val.lower() in ("1", "true", "yes") else ""
            else:
                print(f"unknown key: {key} (use threshold, defer, maxfails, force, keep, debug)")
                return
            LogUtils.print(f"[cache_compact] {key}={val}")

        else:
            print("usage: /cache-compact [status|enable [N]|disable|set <key> <val>]")

    ctx.register_command(
        "cache-compact", _handle_cc, "Manage cache compaction (enable/disable/set)"
    )

    if Config.debug():
        enabled = cfg["threshold"] > 0
        mode = "force" if cfg["force"] else "soft"
        LogUtils.print(
            f"[+] cache_compact plugin loaded ({'enabled' if enabled else 'disabled'})"
        )
        if enabled:
            LogUtils.print(
                f"  - threshold: {cfg['threshold']}%  defer: {cfg['defer']}%  maxfails: {cfg['max_fails']}  keep: {cfg['keep_percent']}%  mode: {mode}"
            )
