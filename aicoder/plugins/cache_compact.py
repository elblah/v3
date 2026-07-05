"""
cache_compact.py - Cache-aware cooperative compaction

Two paths:
- Passive: system-prompt nudge lets AI voluntarily emit [SUMMARY] at breaks.
- Active:  at threshold (default 50%), appends a <system-reminder> suggestion
           to the user's message (no extra round trip). Set CACHE_COMPACT_FORCE=1
           for forceful "COMPACTION MODE" instruction instead of soft suggestion.

Tier boundaries (coexists with existing tiers):
- [CACHE_COMPACT_THRESHOLD, CACHE_COMPACT_DEFER) -> this plugin (cooperative)
- [80%, 95%)  -> compact_strategy plugin (forced, untouched)
- [95%, 100%] -> core auto-compact (brutal, untouched)

Detection: any assistant message beginning with [SUMMARY] triggers a swap to
[system, summary] + prune_old_summaries + increment_compaction_count.

Env:
- CACHE_COMPACT_THRESHOLD  trigger % of context size (default 50, 0 = disabled)
- CACHE_COMPACT_DEFER      upper bound % to defer to existing tiers (default 80)
- CACHE_COMPACT_MAXFAILS   consecutive failures before standing down (default 3)
- CACHE_COMPACT_FORCE=1    use forceful "COMPACTION MODE" instruction instead of soft suggestion
- CACHE_COMPACT_DEBUG=1    verbose log: per-msg fail count & suggestion events
"""

import os
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

import re

SUMMARY_TAG = "[SUMMARY]"

PASSIVE_INSTRUCTION = """=== CONTEXT SELF-COMPACTION (protocol) ===
When context grows or at a milestone, emit exactly `[SUMMARY]` as the first printable content of your response — no markdown, no `**` bold, no quotes, no indentation, no whitespace prefix. It's a literal tag read by internal tooling. Follow with a self-contained summary of task, progress, decisions, files, next steps. This resets context to just [system, summary]; everything else is discarded. Use at natural breakpoints."""

# Detect [SUMMARY] even if dumb AIs wrap it in markdown formatting
_RE_SUMMARY_LEADING = re.compile(r'^[*_`#\s]*(\[SUMMARY\])')

COMPACT_INSTRUCTION = "Context growing. If at a breakpoint, emit [SUMMARY] with what to remember."

FORCE_COMPACT_INSTRUCTION = (
    "COMPACTION MODE: your context is large. Produce a self-contained summary of the "
    "entire conversation above. Begin your response with the literal token `[SUMMARY]` "
    "followed by the summary. Do not call any tools. Output only the summary - it will "
    "become your entire memory of the session, so include everything you must remember: "
    "task, progress, key decisions with rationale, file paths and line numbers, current "
    "state, failed approaches, next steps."
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
    """True if [SUMMARY] is the first printable content (ignoring leading whitespace/markdown)."""
    if SUMMARY_TAG not in text:
        return False
    return bool(_RE_SUMMARY_LEADING.match(text))


def _compact(messages, app, state):
    """Replace history with [system, summary], reset state."""
    system_msg = messages[0] if messages[0].get("role") == "system" else None
    # If there's already a [SUMMARY] user message, keep it as-is
    last = messages[-1]
    summary_content = _content_str(last.get("content", ""))
    summary_msg = {"role": "user", "content": summary_content}
    new_msgs = [system_msg, summary_msg] if system_msg else [summary_msg]
    before = len(messages)
    app.message_history.set_messages(new_msgs)
    app.message_history.prune_old_summaries()
    app.message_history.increment_compaction_count()
    state["awaiting"] = False
    state["fails"] = 0
    c = Config.colors
    LogUtils.print(
        f"{c['bold']}{c['green']}[cache_compact] accepted [SUMMARY] "
        f"-> {before} to {len(new_msgs)} msgs{c['reset']}"
    )


def create_plugin(ctx):
    app = ctx.app

    cfg = {
        "threshold": int(os.environ.get("CACHE_COMPACT_THRESHOLD", "50")),
        "defer": int(os.environ.get("CACHE_COMPACT_DEFER", "80")),
        "max_fails": int(os.environ.get("CACHE_COMPACT_MAXFAILS", "3")),
        "force": os.environ.get("CACHE_COMPACT_FORCE", "").lower() in ("1", "true", "yes"),
    }

    state = {"awaiting": False, "fails": 0}

    def _on_system_prompt_append():
        if cfg["threshold"] > 0:
            return PASSIVE_INSTRUCTION
        return None

    def _on_assistant_message_added(message):
        """after_assistant_message_added hook - detect [SUMMARY] immediately."""
        if cfg["threshold"] <= 0:
            return
        content = _content_str(message.get("content", ""))
        if content and _is_summary_first_printable(content):
            # Don't compact if this message also has tool_calls — the tool
            # results haven't been added yet and would become orphaned,
            # causing "tool result's tool id not found" (2013) on next request.
            if message.get("tool_calls"):
                if os.environ.get("CACHE_COMPACT_DEBUG"):
                    c = Config.colors
                    LogUtils.print(
                        f"{c['yellow']}[cache_compact] [SUMMARY] had tool_calls, "
                        f"deferring compaction{c['reset']}"
                    )
                return
            _compact(app.message_history.get_messages(), app, state)

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
                    f"{c['yellow']}[cache_compact] AI did not emit [SUMMARY] "
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
                f"-> appended [SUMMARY] suggestion{c['reset']}"
            )
        return f"{user_input}\n\n<system-reminder>\n{instruction}\n</system-reminder>"

    ctx.register_hook("on_system_prompt_append", _on_system_prompt_append)
    ctx.register_hook("after_assistant_message_added", _on_assistant_message_added)
    ctx.register_hook("after_user_prompt", _suggest_compaction)

    def _on_info(sub: str) -> None:
        if sub == "config":
            c = Config.colors
            status = "awaiting" if state["awaiting"] else "idle"
            enabled = cfg["threshold"] > 0
            print(f"{c['bold']}cache_compact:{c['reset']} {'enabled' if enabled else 'disabled'}")
            if enabled:
                mode = "force" if cfg["force"] else "soft"
                print(f"  threshold: {cfg['threshold']}%  defer: {cfg['defer']}%  maxfails: {cfg['max_fails']}")
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
            print(f"{c['bold']}cache_compact:{c['reset']} {'enabled' if enabled else 'disabled'}")
            if enabled:
                print(f"  threshold: {cfg['threshold']}%  defer: {cfg['defer']}%  maxfails: {cfg['max_fails']}")
                print(f"  mode: {mode}  state: {status}  fails: {state['fails']}")
            else:
                print(f"  threshold: 0 (disabled)  defer: {cfg['defer']}%  maxfails: {cfg['max_fails']}")

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
                print("  keys: threshold, defer, maxfails, force")
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
            else:
                print(f"unknown key: {key} (use threshold, defer, maxfails, force)")
                return
            LogUtils.print(f"[cache_compact] {key}={val}")

        else:
            print("usage: /cache-compact [status|enable [N]|disable|set <key> <val>]")

    ctx.register_command("cache-compact", _handle_cc, "Manage cache compaction (enable/disable/set)")

    if Config.debug():
        enabled = cfg["threshold"] > 0
        mode = "force" if cfg["force"] else "soft"
        LogUtils.print(f"[+] cache_compact plugin loaded ({'enabled' if enabled else 'disabled'})")
        if enabled:
            LogUtils.print(
                f"  - threshold: {cfg['threshold']}%  defer: {cfg['defer']}%  maxfails: {cfg['max_fails']}  mode: {mode}"
            )
