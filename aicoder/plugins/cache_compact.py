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
"""

import os
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

SUMMARY_TAG = "[SUMMARY]"

PASSIVE_INSTRUCTION = """=== CONTEXT SELF-COMPACTION ===
You can reset/compact your context at any logical breakpoint by sending a message that begins with the literal token `[SUMMARY]` followed by a self-contained summary of everything you must remember (task, progress, key decisions, file paths and line numbers, current state, next steps). That summary then becomes your entire memory of the session; everything else is discarded. Use this proactively when context is growing large or a major task milestone is complete."""

COMPACT_INSTRUCTION = (
    "Context is getting large. If you've reached a natural breakpoint, consider emitting "
    "a `[SUMMARY]` to compact — it'll become your entire memory of the session, so include "
    "everything you must remember: task, progress, key decisions, file paths, current state, "
    "next steps. If you're mid-task, just continue normally and compact when you hit a "
    "stopping point."
)

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

    def _transform_user_input(user_input: str) -> str:
        """after_user_prompt hook - detect [SUMMARY], suggest compaction"""
        messages = app.message_history.get_messages()
        if not messages:
            return user_input

        # Check if AI just emitted [SUMMARY] -> compact history
        last = messages[-1]
        last_content = _content_str(last.get("content", "")) if last.get("role") == "assistant" else ""
        if last_content.startswith(SUMMARY_TAG):
            system_msg = messages[0] if messages[0].get("role") == "system" else None
            summary_msg = {"role": "user", "content": last_content}
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
            return user_input

        if cfg["threshold"] <= 0:
            return user_input

        if state["awaiting"]:
            state["awaiting"] = False
            state["fails"] += 1
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

        # Don't pollute commands
        if user_input.startswith("/"):
            return user_input

        instruction = FORCE_COMPACT_INSTRUCTION if cfg["force"] else COMPACT_INSTRUCTION
        state["awaiting"] = True
        c = Config.colors
        LogUtils.print(
            f"{c['bold']}{c['cyan']}[cache_compact] {pct:.0f}% context "
            f"-> appended [SUMMARY] suggestion{c['reset']}"
        )
        return f"{user_input}\n\n<system-reminder>\n{instruction}\n</system-reminder>"

    ctx.register_hook("on_system_prompt_append", _on_system_prompt_append)
    ctx.register_hook("after_user_prompt", _transform_user_input)

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
