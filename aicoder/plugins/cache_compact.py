"""
cache_compact.py - Cache-aware cooperative compaction

Compaction that reuses prompt-cache by running as a normal cached turn instead
of a fresh specialized invocation.

Two paths, one file:
- Passive: system-prompt nudge lets AI voluntarily emit [SUMMARY] at breaks.
- Active:  at threshold (default 50%), before user handoff, injects a compaction
           instruction via set_next_prompt -> runs as a cached turn.

Tier boundaries (coexists with existing tiers, does NOT replace them):
- [CACHE_COMPACT_THRESHOLD, CACHE_COMPACT_DEFER) -> this plugin (cooperative)
- [80%, 95%)  -> compact_strategy plugin (forced, untouched)
- [95%, 100%] -> core auto-compact (brutal, untouched)

Detection: any assistant message beginning with [SUMMARY] triggers a swap to
[system, summary] + prune_old_summaries + increment_compaction_count.

Env:
- CACHE_COMPACT_THRESHOLD  trigger % of context size (default 50, 0 = disabled)
- CACHE_COMPACT_DEFER      upper bound % to defer to existing tiers (default 80)
- CACHE_COMPACT_MAXFAILS   consecutive failures before standing down (default 3)
"""

import os
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

SUMMARY_TAG = "[SUMMARY]"

PASSIVE_INSTRUCTION = """=== CONTEXT SELF-COMPACTION ===
You can reset/compact your context at any logical breakpoint by sending a message that begins with the literal token `[SUMMARY]` followed by a self-contained summary of everything you must remember (task, progress, key decisions, file paths and line numbers, current state, next steps). That summary then becomes your entire memory of the session; everything else is discarded. Use this proactively when context is growing large or a major task milestone is complete."""

COMPACT_INSTRUCTION = (
    "COMPACTION MODE: your context is large. Produce a self-contained summary of the entire "
    "conversation above. Begin your response with the literal token `[SUMMARY]` followed by "
    "the summary. Do not call any tools. Output only the summary - it will become your entire "
    "memory of the session, so include everything you must remember: task, progress, key "
    "decisions with rationale, file paths and line numbers, current state, failed approaches, "
    "next steps."
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

    threshold = int(os.environ.get("CACHE_COMPACT_THRESHOLD", "50"))
    defer_pct = int(os.environ.get("CACHE_COMPACT_DEFER", "80"))
    max_fails = int(os.environ.get("CACHE_COMPACT_MAXFAILS", "3"))

    if threshold <= 0:
        return {}

    state = {"awaiting": False, "fails": 0}

    def _on_system_prompt_append():
        return PASSIVE_INSTRUCTION

    def _before_user_prompt():
        messages = app.message_history.get_messages()
        if not messages:
            return

        last = messages[-1]
        last_content = _content_str(last.get("content", "")) if last.get("role") == "assistant" else ""
        accepted = last_content.startswith(SUMMARY_TAG)

        if accepted:
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
            return

        if state["awaiting"]:
            state["awaiting"] = False
            state["fails"] += 1
            c = Config.colors
            LogUtils.print(
                f"{c['yellow']}[cache_compact] AI did not emit [SUMMARY] "
                f"({state['fails']}/{max_fails}){c['reset']}"
            )

        current = app.stats.current_prompt_size or 0
        max_size = Config.context_size()
        pct = (current / max_size * 100) if max_size else 0

        if pct < threshold:
            state["fails"] = 0
            return
        if pct >= defer_pct:
            return
        if state["fails"] >= max_fails:
            return

        app.set_next_prompt(COMPACT_INSTRUCTION)
        state["awaiting"] = True
        c = Config.colors
        LogUtils.print(
            f"{c['bold']}{c['cyan']}[cache_compact] {pct:.0f}% context "
            f"-> requesting [SUMMARY] (cached turn){c['reset']}"
        )

    ctx.register_hook("on_system_prompt_append", _on_system_prompt_append)
    ctx.register_hook("before_user_prompt", _before_user_prompt)

    def _on_info(sub: str) -> None:
        if sub == "config":
            c = Config.colors
            status = "awaiting" if state["awaiting"] else "idle"
            print(f"{c['bold']}cache_compact:{c['reset']}")
            print(f"  threshold: {threshold}%  defer: {defer_pct}%  maxfails: {max_fails}")
            print(f"  state: {status}  fails: {state['fails']}")

    ctx.register_hook("on_info", _on_info)

    if Config.debug():
        LogUtils.print("[+] cache_compact plugin loaded")
        LogUtils.print(
            f"  - threshold: {threshold}%  defer at: {defer_pct}%  maxfails: {max_fails}"
        )
