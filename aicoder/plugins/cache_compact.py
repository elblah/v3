"""
cache_compact.py - Cache-aware compaction

One injection path: after_assistant_message_added.
- [COMPACT_SUMMARY] tag detected -> compact.
- No tag + context past threshold -> inject standalone <system-reminder> into
  history; re-injected on every non-complying reply. AI must comply.
- Continuation turn after a fulfilled compaction -> guard cleared, no re-inject.

Env:
- CACHE_COMPACT_THRESHOLD   trigger % of context size (default 65, 0 = disabled)
- CACHE_COMPACT_KEEP_PERCENT  keep N% of recent context after [SUMMARY] (default 15)
- CACHE_COMPACT_DEBUG=1     verbose log: injection events
"""

import os
import re

from aicoder.core.config import Config
from aicoder.core.nudges import add_nudge, clear_nudges
from aicoder.utils.log import LogUtils

SUMMARY_TAG = "[SUMMARY]"
COMPACT_TAG = "[COMPACT_SUMMARY]"

PASSIVE_INSTRUCTION = """If you're at a natural breakpoint and the conversation feels long, you may optionally begin your response with [COMPACT_SUMMARY] as your VISIBLE reply text (never inside your reasoning/thinking). If you do, follow with a summary of task, progress, decisions, files, next steps. This replaces everything else in context with just that summary. Use rarely — only when genuinely helpful to save space."""

# Normalize the detected leading tag -> [SUMMARY] (whitespace prefix tolerated;
# match is strict anyway since detection now requires the unwrapped tag)
_RE_COMPACT_TAG_LEADING = re.compile(r"^[*_`#\s]*(\[COMPACT_SUMMARY\])")
_RE_SYSTEM_REMINDER = re.compile(r"\n\n<system-reminder>.*?</system-reminder>", re.DOTALL)

FORCE_COMPACT_INSTRUCTION = (
    "⚠ SYSTEM REQUEST — NOT OPTIONAL. COMPACTION REQUIRED NOW. ⚠\n"
    "Context limit approaching. You MUST comply:\n"
    "1. Do NOT call any tools\n"
    "2. Begin your VISIBLE reply with [COMPACT_SUMMARY] — never put the tag or "
    "summary inside your reasoning/thinking block; the visible message must "
    "contain the full summary text\n"
    "3. Write a self-contained summary of the ENTIRE conversation above\n"
    "4. Include: task, progress, key decisions with rationale, file paths and line numbers, "
    "current state, failed approaches, next steps\n"
    "5. This summary becomes your ENTIRE memory — omit nothing critical\n\n"
    "OUTPUT ONLY THE SUMMARY AS YOUR REPLY. DO NOT CONTINUE WORKING. COMPLY NOW."
)


# Regex to find [COMPACT_SUMMARY] at line start. Strict: leading whitespace
# only, tag followed by whitespace or EOL. Same-line summaries like
# "[COMPACT_SUMMARY] <summary>" are accepted.
# Deliberately NO markdown-wrapper allowance (*_`#): a backtick- or
# bold-quoted tag at line start is byte-identical to a wrapped tag, so
# quoting "[COMPACT_SUMMARY]" in an explanation would false-positive and
# destroy the conversation. False negatives are safe (nudge re-injects);
# false positives are not.
_RE_COMPACT_TAG_LINE = re.compile(r"(?m)^\s*\[COMPACT_SUMMARY\](?=\s|$)")


def _content_str(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text", "")
    return ""


def _is_compaction_request(msg) -> bool:
    """True for plugin-injected compaction requests: user messages that are a
    bare <system-reminder>. Kept out of the recent window so a fulfilled request
    isn't re-executed every turn.
    """
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    if not isinstance(content, str):
        return False
    return content.strip().startswith("<system-reminder>")


def _find_compact_tag(text: str) -> int:
    """Find [COMPACT_SUMMARY] at line start. Returns position of the tag, or -1."""
    if COMPACT_TAG not in text:
        return -1
    m = _RE_COMPACT_TAG_LINE.search(text)
    return m.start() if m else -1


def _reasoning_fields() -> list:
    """Field names that may hold provider reasoning content."""
    override = Config.get_reasoning_field()
    fields = [override] if override else []
    for field in Config.get_possible_reasoning_fields():
        if field not in fields:
            fields.append(field)
    return fields


def _reasoning_tag_text(message) -> str:
    """Return reasoning content carrying [COMPACT_SUMMARY], or ''."""
    for field in _reasoning_fields():
        value = message.get(field)
        if not value:
            continue
        text = value if isinstance(value, str) else _content_str(value)
        if text and _find_compact_tag(text) != -1:
            return text
    return ""


def _strip_before_tag(content: str) -> str:
    """Strip everything before the line containing [COMPACT_SUMMARY]."""
    idx = _find_compact_tag(content)
    if idx > 0:
        return content[idx:]
    return content


def _is_summary_first_printable(text: str) -> bool:
    """True if [COMPACT_SUMMARY] starts a line (own line or same-line summary)."""
    return _find_compact_tag(text) != -1


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


def _compact(messages, app, state, keep_percent=0, from_reasoning=False):
    """Replace history with [system, summary, ...recent], reset state."""
    system_msg = messages[0] if messages[0].get("role") == "system" else None
    # If there's already a [SUMMARY] user message, keep it as-is
    last = messages[-1]
    summary_content = _content_str(last.get("content", ""))
    summary_content = _strip_before_tag(summary_content)
    # Normalize: convert [COMPACT_SUMMARY] → [SUMMARY]
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
            m for m in messages[1:-1] if not _is_compaction_request(m)
        ]
        recent = _select_recent_by_percent(
            candidates, keep_percent, Config.context_size()
        )
    new_msgs = ([system_msg, summary_msg] if system_msg else [summary_msg]) + recent
    before = len(messages)
    app.message_history.set_messages(new_msgs)
    app.message_history.prune_old_summaries()
    app.message_history.increment_compaction_count()
    app.set_next_prompt(
        "<system-reminder>\n"
        "SYSTEM: Context was compacted. The [SUMMARY] above is YOUR OWN summary "
        "from a previous context window — you wrote it, not the user. "
        "The compaction request has been fulfilled — do NOT compact again. "
        "This is an automatic continuation prompt, not a user message. "
        "Resume your task from where you left off.\n"
        "</system-reminder>"
    )
    state["cont_prompt"] = True  # continuation prompt pending — guard re-compaction
    c = Config.colors
    keep_info = f", kept {len(recent)} recent" if recent else ""
    source = " (from reasoning)" if from_reasoning else ""
    LogUtils.print(
        f"\n\n{c['bold']}{c['green']}[cache_compact] accepted [COMPACT_SUMMARY]"
        f"{source} -> {before} to {len(new_msgs)} msgs{keep_info}{c['reset']}\n"
    )


def _compact_keep_assistant(
    app, state, assistant_msg, keep_percent=0, from_reasoning=False
):
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
                m for m in messages[1:idx] if not _is_compaction_request(m)
            ]
            recent = _select_recent_by_percent(
                candidates, keep_percent, Config.context_size()
            )
    prefix = [system_msg] if system_msg else []
    # Normalize assistant message: [COMPACT_SUMMARY] → [SUMMARY] for internal storage
    normalized = dict(assistant_msg)
    raw = _content_str(normalized.get("content", ""))
    raw = _strip_before_tag(raw)
    m = _RE_COMPACT_TAG_LEADING.match(raw)
    if m:
        normalized["content"] = SUMMARY_TAG + raw[m.end(1):]
    new_msgs = prefix + recent + [normalized]
    before = len(messages)
    app.message_history.set_messages(new_msgs)
    app.message_history.prune_old_summaries()
    app.message_history.increment_compaction_count()
    app.set_next_prompt(
        "<system-reminder>\n"
        "SYSTEM: Context was compacted. The [SUMMARY] above is YOUR OWN summary "
        "from a previous context window — you wrote it, not the user. "
        "The compaction request has been fulfilled — do NOT compact again. "
        "This is an automatic continuation prompt, not a user message. "
        "Resume your task from where you left off.\n"
        "</system-reminder>"
    )
    state["cont_prompt"] = True  # continuation prompt pending — guard re-compaction
    c = Config.colors
    keep_info = f", kept {len(recent)} recent" if recent else ""
    source = " (from reasoning)" if from_reasoning else ""
    LogUtils.print(
        f"\n\n{c['bold']}{c['green']}[cache_compact] accepted [COMPACT_SUMMARY]"
        f"{source} (with tool_calls) -> {before} to {len(new_msgs)} msgs"
        f"{keep_info}{c['reset']}\n"
    )


def create_plugin(ctx):
    app = ctx.app

    cfg = {
        "threshold": int(os.environ.get("CACHE_COMPACT_THRESHOLD", "65")),
        "keep_percent": int(os.environ.get("CACHE_COMPACT_KEEP_PERCENT", "15")),
    }

    state = {"cont_prompt": False}

    def _on_after_compaction():
        """Any compaction (compact_strategy, core auto-compact, /compact)
        fulfilled context pressure. Remove all [NUDGE:COMPACTION] reminders —
        they are stale: the AI may comply and re-compact. Also guard like our
        own _compact: a summary in response to a stale reminder is refused and
        dropped, and the next normal reply clears the guard without injecting."""
        clear_nudges(app, "COMPACTION")
        state["cont_prompt"] = True

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
        from_reasoning = False
        if not is_summary:
            reasoning = _reasoning_tag_text(message)
            if reasoning:
                promoted = reasoning[_find_compact_tag(reasoning):]
                if content:
                    promoted += "\n\n" + content
                message["content"] = promoted
                for field in _reasoning_fields():
                    message.pop(field, None)
                content = promoted
                is_summary = True
                from_reasoning = True
                c = Config.colors
                LogUtils.print(
                    f"\n{c['bold']}{c['brightYellow']}[cache_compact]{c['reset']} "
                    f"summary found in reasoning field (show-reasoning may be "
                    f"off) — promoted to visible content:\n{promoted}"
                )
        if is_summary:
            if state["cont_prompt"]:
                # Summary right after a fulfilled compaction = AI re-compacting
                # in response to the continuation prompt (14->13->... loop).
                # Refuse and drop the junk message. Guard stays set: a stale
                # reminder compliance or empty-retry must not unlock a fresh
                # injection cycle — only a real (non-summary) reply clears it.
                if not message.get("tool_calls"):
                    msgs = app.message_history.get_messages()
                    if msgs and msgs[-1] is message:
                        app.message_history.set_messages(msgs[:-1])
                return
            if message.get("tool_calls"):
                _compact_keep_assistant(
                    app, state, message, cfg["keep_percent"], from_reasoning
                )
            else:
                _compact(
                    app.message_history.get_messages(), app, state,
                    cfg["keep_percent"], from_reasoning
                )
        else:
            if state["cont_prompt"]:
                # Continuation turn after a fulfilled compaction — done. Clear
                # the guard so future compactions still work. Do NOT inject:
                # context was just compacted, and re-injecting would re-request
                # a compaction the AI already fulfilled.
                state["cont_prompt"] = False
                return

            # Inject a standalone request when context is past threshold.
            # Fires per assistant reply — covers user turns and tool loops alike.
            # No stand-down: the AI must comply.
            current = app.stats.current_prompt_size or 0
            max_size = Config.context_size()
            pct = (current / max_size * 100) if max_size else 0

            if pct < cfg["threshold"]:
                return

            add_nudge(app, "COMPACTION", FORCE_COMPACT_INSTRUCTION)
            state["cont_prompt"] = False  # new compaction cycle — reset loop guard
            if os.environ.get("CACHE_COMPACT_DEBUG"):
                c = Config.colors
                LogUtils.print(
                    f"{c['bold']}{c['cyan']}[cache_compact] {pct:.0f}% context "
                    f"-> injected compaction request{c['reset']}"
                )



    def _on_info(sub: str) -> None:
        if sub == "config":
            c = Config.colors
            enabled = cfg["threshold"] > 0
            print(
                f"{c['bold']}cache_compact:{c['reset']} {'enabled' if enabled else 'disabled'}"
            )
            if enabled:
                print(
                    f"  threshold: {cfg['threshold']}%  keep: {cfg['keep_percent']}%  mode: force"
                )

    ctx.register_hook("on_info", _on_info)

    ctx.register_hook("after_compaction", _on_after_compaction)
    ctx.register_hook("on_system_prompt_append", _on_system_prompt_append)
    ctx.register_hook("after_assistant_message_added", _on_assistant_message_added)

    if Config.debug():
        enabled = cfg["threshold"] > 0
        LogUtils.print(
            f"[+] cache_compact plugin loaded ({'enabled' if enabled else 'disabled'})"
        )
        if enabled:
            LogUtils.print(
                f"  - threshold: {cfg['threshold']}%  keep: {cfg['keep_percent']}%  mode: force"
            )
