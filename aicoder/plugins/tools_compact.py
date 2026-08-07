"""
tools_compact.py - AI-initiated micro-compaction of tool call/result pairs

The AI emits `[COMPACT_SUMMARY:TOOLS]` at the start of a visible reply; the
plugin consumes all consecutive (assistant message with tool_calls + its tool
results) pairs preceding that reply, keeping the reply as the summary. If the
reply made no tool calls, the turn is continued automatically ("Continue.")
so the AI can keep working with a compacted history.

Nudge: when the live tool loop since the AI last finished its turn (handed
the prompt back) reaches TOOLS_COMPACT_LOOP_PCT % of the context budget
(loop cost, not total prompt size), ONE hard <system-reminder> demand is
injected per loop cycle —
imperative phrasing, "THIS IS MANDATORY". No light/optional nudges: the
optional capability note lives in the system prompt (PASSIVE_INSTRUCTION)
and the nudge only fires at the threshold. If the triggering tool result
landed mid-history (open chain after it), the nudge is deferred and delivered
at the next completed assistant reply — never dropped, never between a
tool_calls message and its results.
Not part of forced-compaction machinery. cache_compact
is unaffected: its tag regex does not match `:TOOLS` (verified both ways),
standalone reminders are skipped by the backward scan, and its state machine
only inspects the last assistant message.

Env:
- TOOLS_COMPACT_ENABLED=1  opt-in master switch (default: OFF — plugin loads
                           as a no-op, registers nothing)
- TOOLS_COMPACT_LOOP_PCT     hard nudge when loop cost reaches N% of the context
                             budget (0=off). Loop cost — not total
                             prompt size — is the trigger: a big prompt with a
                             tiny loop doesn't need tools compaction.
- TOOLS_COMPACT_CONTINUE     auto-continue turn after compaction
- TOOLS_COMPACT_SHOW_BUDGET=1 show live loop cost in the context bar as a
                             dimmed `lb:N` suffix
- TOOLS_COMPACT_DEBUG=1      verbose log

Runtime control (session-only, not persisted — like /cs):
- `/toolcompact`            status
- `/toolcompact on|off`     enable/disable the nudge (and passive instruction)
- `/toolcompact <tokens>`   absolute budget, e.g. 20000, 20k, 1.5m (min 1000)
- `/toolcompact pct <N>`    budget as N% of the live context budget (0 = off)
- `/toolcompact reset`      back to env defaults
"""

import os
import re

from aicoder.core.config import Config
from aicoder.core.nudges import add_nudge
from aicoder.core.token_estimator import _message_cache
from aicoder.utils.log import LogUtils

TAG = "[COMPACT_SUMMARY:TOOLS]"

# Detect the tag at line start (leading whitespace/markdown allowed).
# Disjoint from cache_compact's [COMPACT_SUMMARY] regex: its lookahead
# ([\s*_`#]|$) fails on ':' — verified both directions.
_RE_TAG_LINE = re.compile(r"(?m)^[\s*_`#]*\[COMPACT_SUMMARY:TOOLS\](?=[\s*_`#]|$)")

PASSIVE_INSTRUCTION = (
    "`[COMPACT_SUMMARY:TOOLS]` is available: begin a VISIBLE reply with it "
    "(never inside your reasoning/thinking) to replace the preceding tool "
    "call/result loop with your summary. The platform consumes the loop pairs, "
    "keeps your reply as the summary, and automatically continues your turn. "
    "Make the summary self-contained: what the tools did, key findings, "
    "decisions, open threads, next steps. Scope: only the loop since the "
    "previous summary — earlier summaries and their tool results are kept, "
    "never replaced. This is NOT `[COMPACT_SUMMARY]` "
    "(full-conversation compaction) — only tool-loop pairs are removed."
)

HARD_NUDGE = (
    "TOOLS COMPACTION REQUIRED NOW. Your tool loop has consumed {cost} tokens "
    "({pct:.0f}% of the {max_size}-token context window) and it is resubmitted "
    "on every request. Begin your next VISIBLE reply with "
    "[COMPACT_SUMMARY:TOOLS] (never inside your reasoning/thinking) to consume "
    "this loop and free the window. THIS IS MANDATORY — do not continue "
    "working without compacting it."
)


def _content_str(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text", "")
    return ""


def _msg_tokens(msg):
    tokens = _message_cache.get(id(msg), 0)
    if tokens:
        return tokens
    return max(1, len(_content_str(msg.get("content", ""))) // 4)


def _is_standalone_reminder(msg) -> bool:
    """True for plugin-injected system reminders (nudges, forced compaction).
    Duplicated from cache_compact._is_compaction_request — sibling imports are
    brittle under plugin_<name> importlib loading; ~15 lines is the safe price.
    """
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    if not isinstance(content, str):
        return False
    return content.strip().startswith("<system-reminder>")


def _find_tag(text: str) -> int:
    """Position of [COMPACT_SUMMARY:TOOLS] at line start, or -1."""
    if TAG not in text:
        return -1
    m = _RE_TAG_LINE.search(text)
    return m.start() if m else -1


def _find_parent_assistant(msgs, tool_call_id):
    """Most recent assistant message whose tool_calls include tool_call_id,
    searching back to the last real user message (results never cross a user
    turn; standalone reminders may sit between a pair and are skipped)."""
    if not tool_call_id:
        return None
    for m in reversed(msgs):
        role = m.get("role")
        if role == "user":
            if _is_standalone_reminder(m):
                continue
            return None
        if role == "assistant":
            for tc in m.get("tool_calls") or []:
                if tc.get("id") == tool_call_id:
                    return m
    return None


def _scan_pairs(msgs, tag_idx):
    """Backward scan from the message before the tag reply. Returns
    (start_index_of_first_consumed_message, pair_count), or (None, 0) if no
    complete pair exists. Skips standalone <system-reminder> user messages;
    stops at real user content / plain assistant messages / previous summary
    replies (any assistant message carrying the tag — its own results must
    survive) / unknown roles.
    """
    start = None
    pairs = 0
    i = tag_idx - 1
    while i >= 0:
        m = msgs[i]
        role = m.get("role")
        if role == "user":
            if _is_standalone_reminder(m):
                i -= 1
                continue
            break
        if role == "assistant":
            if m.get("tool_calls"):
                if _find_tag(_content_str(m.get("content"))) != -1:
                    break  # earlier summary — loop boundary, keep it + its results
                start = i
                pairs += 1
            else:
                break
        elif role != "tool":
            break  # system/unknown role — defensive stop
        i -= 1
    if start is None:
        return None, 0
    return start, pairs


def create_plugin(ctx):
    if os.environ.get("TOOLS_COMPACT_ENABLED", "0") != "1":
        return  # disabled by default — opt-in, no hooks/commands registered
    app = ctx.app

    cfg = {
        "enabled": True,
        "loop_pct": int(os.environ.get("TOOLS_COMPACT_LOOP_PCT", "25")),
        "continuation": os.environ.get("TOOLS_COMPACT_CONTINUE", "1") != "0",
        "show_budget": os.environ.get("TOOLS_COMPACT_SHOW_BUDGET", "0") == "1",
    }

    state = {
        "enabled": cfg["enabled"],   # runtime switch — /toolcompact on|off (session-only)
        "budget": None,              # runtime absolute budget in tokens (None = pct mode)
        "pct": None,                 # runtime budget as % of context (None = env pct)
        "loop_cost": 0,             # token estimate of live tool pairs since reset
        "nudge_fired": False,       # hard nudge issued for the current loop cycle
        "pending_nudge": False,     # nudge owed but blocked mid-chain — deliver at safe spot
        "continuation_armed": False,  # tag reply compacted; continue pending
        "counted_parents": set(),   # assistant ids already added to loop_cost
    }

    def _budget_pct() -> float:
        """Effective nudge percentage: runtime override or env default."""
        return state["pct"] if state["pct"] is not None else cfg["loop_pct"]

    def _loop_threshold() -> float:
        """Nudge threshold in tokens: absolute runtime budget if set, else
        _budget_pct()% of the live context budget. Loop cost — not total
        prompt size — is the trigger: a big prompt with a tiny loop doesn't
        need tools compaction."""
        if state["budget"] is not None:
            return state["budget"]
        pct = _budget_pct()
        if pct <= 0:
            return 0
        max_size = Config.context_size()
        if max_size <= 0:
            return 0
        return max_size * pct / 100

    def _reset_loop():
        state["loop_cost"] = 0
        state["counted_parents"].clear()
        state["continuation_armed"] = False
        state["pending_nudge"] = False
        state["nudge_fired"] = False

    def _inject_nudge():
        """Append the hard compaction demand at the history tail. Callers
        guarantee the tail is a completed message (no open tool_calls chain
        after it), so the user-role reminder can never split a pair."""
        if state["nudge_fired"] or state["loop_cost"] <= 0:
            return
        state["nudge_fired"] = True
        max_size = Config.context_size()
        add_nudge(
            app,
            "COMPACTION",
            HARD_NUDGE.format(
                cost=state["loop_cost"],
                pct=(state["loop_cost"] / max_size * 100) if max_size else 0,
                max_size=max_size,
            ),
        )
        if os.environ.get("TOOLS_COMPACT_DEBUG"):
            c = Config.colors
            LogUtils.print(
                f"{c['bold']}{c['brightYellow']}[tools_compact]{c['reset']} "
                f"hard nudge issued (loop cost {state['loop_cost']} tokens)"
            )

    def _on_tool_results_added(tool_message):
        """Accumulate loop cost and nudge once when it crosses the
        threshold (single boundary, no %-step bands). Self-healing: a
        cancelled parallel tool finishing LATE lands after the injected
        nudge, splitting its parent's result chain (providers reject user
        role between tool_calls and results) — relocate the nudge to the
        tail so it always follows a completed result."""
        if not state["enabled"]:
            return
        msgs = app.message_history.get_messages()

        if state["nudge_fired"] and msgs and msgs[-1] is tool_message:
            # Late result: find our nudge (identity scan for the marker; only
            # the LAST nudge can split a chain — older ones sit before a
            # completed assistant reply). If it sits between the arriving
            # result and its parent, move it to the tail. replace_messages
            # (NOT set_messages) assigns in place without firing
            # after_messages_set — that hook would reset the loop budget and
            # signals compaction to core.
            nudge_idx = None
            for i in range(len(msgs) - 1, -1, -1):
                m = msgs[i]
                if (
                    m.get("role") == "user"
                    and _is_standalone_reminder(m)
                    and "TOOLS COMPACTION REQUIRED NOW"
                    in _content_str(m.get("content", ""))
                ):
                    nudge_idx = i
                    break
            if nudge_idx is not None and nudge_idx < len(msgs) - 1:
                parent = _find_parent_assistant(
                    msgs, tool_message.get("tool_call_id")
                )
                p_idx = None
                if parent is not None:
                    for i, m in enumerate(msgs):
                        if m is parent:
                            p_idx = i
                            break
                if p_idx is not None and p_idx < nudge_idx:
                    nudge = msgs.pop(nudge_idx)
                    msgs.append(nudge)
                    app.message_history.replace_messages(msgs)
                    if os.environ.get("TOOLS_COMPACT_DEBUG"):
                        c = Config.colors
                        LogUtils.print(
                            f"{c['bold']}{c['brightYellow']}[tools_compact]{c['reset']} "
                            f"nudge relocated to tail (late result "
                            f"{tool_message.get('tool_call_id')})"
                        )

        state["loop_cost"] += _msg_tokens(tool_message)
        parent = _find_parent_assistant(msgs, tool_message.get("tool_call_id"))
        if parent is not None and id(parent) not in state["counted_parents"]:
            state["counted_parents"].add(id(parent))
            state["loop_cost"] += _msg_tokens(parent)

        threshold = _loop_threshold()
        if (
            not state["nudge_fired"]
            and threshold > 0
            and state["loop_cost"] >= threshold
        ):
            # Only inject when our result is the history tail. If the result
            # was inserted mid-history (an open assistant(tool_calls) chain
            # after it), appending a user message would sit between that
            # chain and its pending results — providers reject that. Defer:
            # the nudge is delivered at the next safe spot (a completed
            # assistant reply) instead of being dropped.
            if not msgs or msgs[-1] is not tool_message:
                state["pending_nudge"] = True
                return
            _inject_nudge()

    def _on_assistant_message_added(message):
        """Deliver deferred nudge at a safe spot; detect the tag; consume
        preceding tool pairs; arm continuation."""
        if not state["enabled"]:
            return
        content = _content_str(message.get("content", ""))
        has_tag = bool(content) and _find_tag(content) >= 0

        if state["pending_nudge"]:
            if has_tag:
                # Compaction supersedes the nudge — loop state resets anyway.
                state["pending_nudge"] = False
            elif not message.get("tool_calls"):
                # Safe spot: this plain reply is the history tail and closes
                # the loop, so the deferred nudge can't split any pair.
                state["pending_nudge"] = False
                _inject_nudge()
            # else: message opens a new chain — stay pending.

        if not has_tag:
            return
        # Tag + tool calls in one reply is safe to consume: the consumed
        # range ends before this message, its own results append after the
        # kept summary, and the late-result guard below covers stragglers.

        msgs = app.message_history.get_messages()
        tag_idx = None
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i] is message:
                tag_idx = i
                break
        if tag_idx is None:
            return

        start, pairs = _scan_pairs(msgs, tag_idx)
        if start is None:
            return  # nothing to consume — leave history untouched

        # A tool result that arrived after the tag reply (late/cancelled
        # tool finishing) would be orphaned by consuming its parent —
        # leave the history untouched instead.
        # consumed_parents: parent tool_call ids in the would-be-consumed range
        consumed_parents = {
            tc.get("id")
            for m in msgs[start:tag_idx]
            if m.get("role") == "assistant"
            for tc in (m.get("tool_calls") or [])
        }
        for m in msgs[tag_idx + 1:]:
            if m.get("role") == "tool" and m.get("tool_call_id") in consumed_parents:
                return

        before = len(msgs)
        freed = sum(_msg_tokens(m) for m in msgs[start:tag_idx])
        kept = dict(message)  # content kept EXACTLY as the AI sent it (tag included)

        app.message_history.set_messages(msgs[:start] + [kept])

        state["loop_cost"] = 0
        state["counted_parents"].clear()
        state["nudge_fired"] = False  # a fresh loop in the same turn may warrant a new demand
        state["continuation_armed"] = cfg["continuation"]
        app.message_history.increment_compaction_count()

        c = Config.colors
        # AI reply content is streamed with end="" (stream_processor.py) — the
        # stream ends mid-line, so start this log on a fresh line.
        LogUtils.print(
            f"\n{c['bold']}{c['green']}[tools_compact] accepted {TAG} "
            f"-> {before} to {start + 1} msgs, freed ~{freed} tokens "
            f"({pairs} tool pair(s)){c['reset']}"
        )

    def _on_after_ai_processing(has_tool_calls):
        """Loop-budget reset point: when the AI finishes its turn (no tool
        calls), the accumulated loop cost is spent -> reset. A Ctrl+C
        interrupt never reaches this hook (session_manager raises out of
        process_with_ai before _handle_post_processing), so an interrupted
        run keeps its budget. Also mid-loop continuation: after a tag reply
        without tool calls, feed "Continue." so the AI can keep working with
        the compacted history."""
        if not state["enabled"]:
            return None
        armed = state["continuation_armed"]
        state["continuation_armed"] = False  # one-shot
        if not has_tool_calls:
            _reset_loop()
        if not armed or has_tool_calls:
            return None
        if not cfg["continuation"]:
            return None
        if app.has_next_prompt():
            return None  # another plugin already set a continuation
        return "Continue."

    def _on_context_bar():
        """lb:N — live loop cost in the context bar, dimmed suffix
        (TOOLS_COMPACT_SHOW_BUDGET=1). Hidden while the nudge is disabled."""
        if not cfg["show_budget"] or not state["enabled"]:
            return None
        c = Config.colors
        return f"{c['dim']}lb:{state['loop_cost']}{c['reset']}"

    def _loop_status() -> str:
        """Human-readable runtime state for /toolcompact (no args)."""
        threshold = _loop_threshold()
        max_size = Config.context_size()
        if state["budget"] is not None:
            mode = f"absolute {threshold:,.0f} tokens"
        else:
            mode = (
                f"{_budget_pct():g}% of {max_size:,} tokens "
                f"(= {threshold:,.0f})"
            )
        return (
            f"[tools_compact] loop nudge {'ENABLED' if state['enabled'] else 'DISABLED'} — "
            f"fires at loop >= {mode} | current loop {state['loop_cost']:,} tokens | "
            f"usage: /toolcompact on | off | <tokens> (e.g. 20k) | pct <N> | reset"
        )

    def _on_toolcompact_command(args_str: str) -> str:
        """Runtime control for loop compaction — session-only, not persisted
        (like /cs). Changes apply immediately to the live nudge threshold."""
        parts = args_str.strip().split()
        if not parts:
            return _loop_status()
        cmd = parts[0].lower()
        if cmd == "on":
            state["enabled"] = True
            return "[tools_compact] loop nudge ENABLED"
        if cmd == "off":
            state["enabled"] = False
            state["pending_nudge"] = False  # don't deliver a stale nudge later
            return "[tools_compact] loop nudge DISABLED"
        if cmd == "reset":
            state["enabled"] = cfg["enabled"]
            state["budget"] = None
            state["pct"] = None
            return "[tools_compact] back to env defaults"
        if cmd == "pct":
            if len(parts) < 2:
                return "[tools_compact] usage: /toolcompact pct <N>  (N = % of context, 0 = off)"
            try:
                pct = float(parts[1])
            except ValueError:
                return f"[tools_compact] invalid pct: {parts[1]}"
            if not 0 <= pct <= 100:
                return "[tools_compact] pct must be 0..100"
            state["pct"] = pct
            state["budget"] = None
            return f"[tools_compact] loop nudge at {pct:g}% of context ({_loop_threshold():,.0f} tokens)"
        try:
            raw = cmd.lower()
            if raw == "default":
                return "[tools_compact] usage: /toolcompact reset (not 'default')"
            if raw.endswith("k"):
                tokens = int(float(raw[:-1]) * 1000)
            elif raw.endswith("m"):
                tokens = int(float(raw[:-1]) * 1000000)
            else:
                tokens = int(raw)
        except ValueError:
            return f"[tools_compact] invalid budget: {cmd}  (e.g. /toolcompact 20k)"
        if tokens < 1000:
            return "[tools_compact] budget too small — minimum 1000 tokens (see /toolcompact pct)"
        state["budget"] = tokens
        state["pct"] = None
        return f"[tools_compact] loop nudge at loop >= {tokens:,} tokens"

    def _on_system_prompt_append():
        if state["enabled"]:
            return PASSIVE_INSTRUCTION
        return None

    def _on_info(sub: str) -> None:
        if sub == "config":
            c = Config.colors
            print(
                f"{c['bold']}tools_compact:{c['reset']} "
                f"{'enabled' if state['enabled'] else 'disabled'}"
            )
            if state["enabled"]:
                threshold = _loop_threshold()
                if state["budget"] is not None:
                    budget = f"loop >= {threshold:,.0f} tokens (absolute)"
                else:
                    budget = (
                        f"loop >= {threshold:,.0f} tokens "
                        f"({_budget_pct():g}% of budget)"
                    )
                print(
                    f"  nudge: hard demand at {budget}  "
                    f"continuation: {'on' if cfg['continuation'] else 'off'}  "
                    f"loop bar: {'on' if cfg['show_budget'] else 'off'}"
                )

    def _on_history_replaced(*_args):
        """Any history replacement invalidates the live loop: reset loop cost
        so a stale nudge can't fire after compaction. Fires on core compact
        paths (after_compaction) AND on cache_compact's direct set_messages
        compaction / loads / /m edits (after_messages_set), which never
        fires after_compaction. Safe at the consume site: set_messages runs
        BEFORE continuation_armed is re-armed."""
        _reset_loop()

    ctx.register_hook("on_info", _on_info)
    ctx.register_hook("on_system_prompt_append", _on_system_prompt_append)
    ctx.register_hook("after_tool_results_added", _on_tool_results_added)
    ctx.register_hook("after_assistant_message_added", _on_assistant_message_added)
    ctx.register_hook("after_ai_processing", _on_after_ai_processing)
    ctx.register_hook("after_compaction", _on_history_replaced)
    ctx.register_hook("after_messages_set", _on_history_replaced)
    ctx.register_hook("on_context_bar", _on_context_bar)
    ctx.register_command(
        "toolcompact",
        _on_toolcompact_command,
        "tools-compaction loop budget: on|off|<tokens>|pct <N>|reset (session-only)",
    )

    if Config.debug():
        LogUtils.print(
            f"[+] tools_compact plugin loaded "
            f"(enabled={cfg['enabled']}, hard nudge at {cfg['loop_pct']}% of budget, "
            f"continuation={cfg['continuation']})"
        )
