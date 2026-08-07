"""Shared nudge helpers: uniform <system-reminder> wrapper with category tag.

Canonical format:

    <system-reminder>
    [NUDGE:TAG]
    body...
    </system-reminder>

Plugins inject via add_nudge() and clear whole categories via clear_nudges()
(e.g. compaction reminders are stale once ANY compaction ran — see
cache_compact's after_compaction hook). Only standalone user messages are
cleared: nudges appended to real user content belong to that turn and are
left alone.
"""

import re

_IS_STANDALONE_RE = re.compile(r"^\s*<system-reminder>")

NUDGE_TAG_RE = re.compile(r"\[NUDGE:([A-Za-z0-9_]+)\]")


def wrap(tag, body):
    """Wrap body in the canonical nudge format."""
    return f"<system-reminder>\n[NUDGE:{tag}]\n{body}\n</system-reminder>"


def add_nudge(app, tag, body):
    """Append a standalone nudge user message to history."""
    app.message_history.add_user_message(wrap(tag, body))


def clear_nudges(app, tag):
    """Remove standalone user messages tagged [NUDGE:tag]. No-op if none."""
    marker = f"[NUDGE:{tag}]"
    msgs = app.message_history.get_messages()
    kept = [
        m
        for m in msgs
        if not (
            m.get("role") == "user"
            and isinstance(m.get("content"), str)
            and _IS_STANDALONE_RE.match(m["content"])
            and marker in m["content"]
        )
    ]
    if len(kept) != len(msgs):
        app.message_history.set_messages(kept)
