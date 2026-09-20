"""Shared nudge helpers: two voices, one category marker.

Reminder voice (default) — advisory, system-ish, skippable by the model:

    <system-reminder>
    [NUDGE:TAG]
    body...
    </system-reminder>

User voice (user_voice=True) — plain user text, carries user authority,
must be obeyed:

    body...

    [NUDGE:TAG]

Plugins inject via add_nudge() and clear whole categories via clear_nudges()
(e.g. compaction reminders are stale once ANY compaction ran — see
cache_compact's after_compaction hook). Only standalone user messages are
cleared: nudges appended to real user content belong to that turn and are
left alone. is_standalone_nudge() is the single matcher for both voices.
"""

import re

_IS_STANDALONE_RE = re.compile(r"^\s*<system-reminder>")

NUDGE_TAG_RE = re.compile(r"\[NUDGE:([A-Za-z0-9_]+)\]")


def wrap(tag, body):
    """Wrap body in the canonical reminder-voice format."""
    return f"<system-reminder>\n[NUDGE:{tag}]\n{body}\n</system-reminder>"


def is_standalone_nudge(msg, tag) -> bool:
    """True for a standalone nudge user message (either voice). Reminder-voice
    nudges appended to real user content are never matched; user-voice is
    matched by its trailing bare marker."""
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return False
    content = msg.get("content")
    if not isinstance(content, str):
        return False
    marker = f"[NUDGE:{tag}]"
    if _IS_STANDALONE_RE.match(content) and marker in content:
        return True
    return content.rstrip().endswith(marker)


def add_nudge(app, tag, body, user_voice=False):
    """Append a standalone nudge user message to history."""
    if user_voice:
        content = f"{body}\n\n[NUDGE:{tag}]"
    else:
        content = wrap(tag, body)
    app.message_history.add_user_message(content)


def clear_nudges(app, tag):
    """Remove standalone user messages tagged [NUDGE:tag]. No-op if none."""
    msgs = app.message_history.get_messages()
    kept = [m for m in msgs if not is_standalone_nudge(m, tag)]
    if len(kept) != len(msgs):
        app.message_history.set_messages(kept)
