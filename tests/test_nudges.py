"""Tests for aicoder/core/nudges.py: canonical wrapper + category clearing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aicoder.core.nudges import NUDGE_TAG_RE, add_nudge, clear_nudges, wrap


class MockHistory:
    def __init__(self):
        self.messages = []

    def get_messages(self):
        return self.messages

    def add_user_message(self, content):
        self.messages.append({"role": "user", "content": content})

    def set_messages(self, msgs):
        self.messages = list(msgs)


class MockApp:
    def __init__(self):
        self.message_history = MockHistory()


def test_wrap_format():
    text = wrap("COMPACTION", "hello")
    assert text == "<system-reminder>\n[NUDGE:COMPACTION]\nhello\n</system-reminder>"


def test_add_nudge_appends_standalone():
    app = MockApp()
    add_nudge(app, "COMPACTION", "do it")
    assert app.message_history.messages[-1]["content"] == wrap("COMPACTION", "do it")


def test_clear_nudges_removes_only_category():
    app = MockApp()
    add_nudge(app, "COMPACTION", "compact now")
    add_nudge(app, "REMINDER", "weekly")
    app.message_history.add_user_message("real question")

    clear_nudges(app, "COMPACTION")

    contents = [m["content"] for m in app.message_history.messages]
    assert not any("compact now" in c for c in contents)
    assert any("weekly" in c for c in contents)
    assert "real question" in contents


def test_clear_nudges_keeps_appended_reminders():
    """Nudge appended to real user content is part of that turn — kept."""
    app = MockApp()
    app.message_history.add_user_message(
        {"role": "user",
         "content": "question\n\n<system-reminder>\n[NUDGE:COMPACTION]\nappended\n</system-reminder>"}
    )
    clear_nudges(app, "COMPACTION")
    assert len(app.message_history.messages) == 1


def test_clear_nudges_noop_when_none():
    app = MockApp()
    app.message_history.add_user_message({"role": "user", "content": "plain"})
    clear_nudges(app, "COMPACTION")
    assert len(app.message_history.messages) == 1


def test_tag_re_matches():
    assert NUDGE_TAG_RE.search("[NUDGE:COMPACTION]").group(1) == "COMPACTION"
    assert NUDGE_TAG_RE.search("plain") is None
