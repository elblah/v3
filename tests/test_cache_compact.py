"""Tests for cache_compact plugin: single-hook injection design.

Injection lives entirely in after_assistant_message_added:
- [COMPACT_SUMMARY] tag -> compact.
- No tag + context past threshold -> standalone <system-reminder> injected into
  history; re-injected on every non-complying reply (no stand-down).
- Guards: below threshold, continuation turn (cont_prompt) never re-injects.
- Refusal: summary right after a fulfilled compaction is dropped.
"""

import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

PLUGIN_PATH = Path(__file__).parent.parent / "aicoder" / "plugins" / "cache_compact.py"


class MockHistory:
    def __init__(self):
        self.messages = []
        self.compaction_count = 0

    def get_messages(self):
        return self.messages

    def add_user_message(self, content):
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, msg):
        self.messages.append(msg)  # same object — hook fires after append

    def set_messages(self, msgs):
        self.messages = list(msgs)

    def prune_old_summaries(self):
        pass

    def increment_compaction_count(self):
        self.compaction_count += 1


class MockApp:
    def __init__(self):
        self.message_history = MockHistory()
        self.stats = types.SimpleNamespace(current_prompt_size=0)
        self.next_prompt = None

    def set_next_prompt(self, prompt):
        self.next_prompt = prompt


@pytest.fixture
def make_ps():
    """Factory: fresh PluginSystem with cache_compact loaded."""
    from aicoder.core.config import Config  # noqa: F401 — freeze env at import

    def _make(threshold="65"):
        os.environ["CACHE_COMPACT_THRESHOLD"] = threshold
        os.environ.setdefault("CACHE_COMPACT_KEEP_PERCENT", "15")
        os.environ["CONTEXT_SIZE"] = "128000"  # isolate from dev env (100000)

        from aicoder.core.plugin_system import PluginSystem

        plugin_system = PluginSystem()
        app = MockApp()
        plugin_system.set_app(app)

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "plugin_cache_compact_test", str(PLUGIN_PATH)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.create_plugin(plugin_system.context)

        return types.SimpleNamespace(ps=plugin_system, app=app, module=module)

    return _make


@pytest.fixture
def ps(make_ps):
    return make_ps()


def _seed(ps):
    """Seed message history (system first)."""
    ps.app.message_history.add_user_message({"role": "system", "content": "sys"})


def _assistant_turn(ps, content, pct_tokens, tool_calls=False):
    """Append an assistant reply and fire the hook (real flow: fires after append)."""
    ps.app.stats.current_prompt_size = pct_tokens
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = [{"id": "t1", "type": "function",
                              "function": {"name": "f", "arguments": "{}"}}]
    ps.app.message_history.add_assistant_message(msg)
    ps.ps.call_hooks("after_assistant_message_added", msg)
    return msg


def _reminders(ps):
    return [m for m in ps.app.message_history.get_messages()
            if m["role"] == "user"
            and isinstance(m.get("content"), str)
            and m["content"].startswith("<system-reminder>")]


def _pct(ps, pct):
    from aicoder.core.config import Config
    return int(Config.context_size() * pct / 100)


def test_is_compaction_request_only_standalone(ps):
    """Standalone reminders filtered; other messages pass through."""
    standalone = {"role": "user", "content": "<system-reminder>\nSYSTEM: COMPACTION REQUIRED.\n</system-reminder>"}
    appended = {"role": "user", "content": "Q\n\n<system-reminder>\nSYSTEM: x\n</system-reminder>"}
    assistant = {"role": "assistant", "content": "reply"}

    assert ps.module._is_compaction_request(standalone)
    assert not ps.module._is_compaction_request(appended)
    assert not ps.module._is_compaction_request(assistant)


def test_no_injection_below_threshold(ps):
    """Reply at 0% context: no reminder injected."""
    _seed(ps)
    _assistant_turn(ps, "plain reply", 0)
    assert _reminders(ps) == []


def test_injection_above_threshold(ps):
    """Reply at 78%: standalone reminder injected into history."""
    _seed(ps)
    _assistant_turn(ps, "plain reply", _pct(ps, 78))
    reminders = _reminders(ps)
    assert len(reminders) == 1
    assert "COMPACTION REQUIRED" in reminders[0]["content"]


def test_injection_uses_forced_instruction(ps):
    """Injection always uses the NOT OPTIONAL instruction (no soft variant)."""
    _seed(ps)
    _assistant_turn(ps, "plain reply", _pct(ps, 78))
    assert "NOT OPTIONAL" in _reminders(ps)[0]["content"]


def test_injection_past_defer_zone(ps):
    """Reply at 85%: still injects — plugin owns its threshold, no defer."""
    _seed(ps)
    _assistant_turn(ps, "plain reply", _pct(ps, 85))
    assert len(_reminders(ps)) == 1


def test_reinject_until_compliance(ps):
    """Every non-complying reply past threshold gets another injection."""
    _seed(ps)
    for i in range(4):
        _assistant_turn(ps, f"reply {i}", _pct(ps, 78))
    assert len(_reminders(ps)) == 4


def test_summary_triggers_compact(ps):
    """Summary reply compacts: [SUMMARY] in history, reminder consumed, continuation set."""
    _seed(ps)
    _assistant_turn(ps, "working...", _pct(ps, 78))
    assert len(_reminders(ps)) == 1

    _assistant_turn(ps, "[COMPACT_SUMMARY] all done", _pct(ps, 78))

    contents = [m["content"] for m in ps.app.message_history.get_messages()]
    assert any(str(c).startswith("[SUMMARY]") for c in contents)
    assert _reminders(ps) == []  # request consumed, excluded from new history
    assert ps.app.next_prompt is not None  # continuation prompt set


def test_quoted_tag_does_not_compact(ps):
    """Aug 8 dogfood regression: AI quoting the tag (backtick-wrapped at line
    start) must NOT compact — byte-identical to an old-style wrapped tag."""
    _seed(ps)
    _assistant_turn(ps, "working...", _pct(ps, 78))
    _assistant_turn(
        ps,
        "`[COMPACT_SUMMARY]` (without `:TOOLS`) is full-conversation "
        "compaction, not the tools variant.",
        _pct(ps, 78),
    )
    assert len(_reminders(ps)) == 2, "quote must not consume the request — non-complying reply gets a fresh injection (old lenient regex would have compacted, dropping the request)"
    assert not any(str(m.get("content", "")).startswith("[SUMMARY]")
                   for m in ps.app.message_history.get_messages())


def test_bold_wrapped_tag_does_not_compact(ps):
    """Markdown-wrapped tag (**...**) is a quote, not a summary — no compact."""
    _seed(ps)
    _assistant_turn(ps, "working...", _pct(ps, 78))
    _assistant_turn(ps, "**[COMPACT_SUMMARY]** is the full-compaction tag.",
                    _pct(ps, 78))
    assert len(_reminders(ps)) == 2  # quote -> no consume -> fresh injection
    assert ps.app.next_prompt is None


def test_own_line_tag_compacts(ps):
    """Canonical form: tag alone on its own line, summary below."""
    _seed(ps)
    _assistant_turn(ps, "working...", _pct(ps, 78))
    _assistant_turn(ps, "[COMPACT_SUMMARY]\nDone: fixed regex, ran tests.",
                    _pct(ps, 78))
    contents = [str(m.get("content", ""))
                for m in ps.app.message_history.get_messages()]
    assert any(c.startswith("[SUMMARY]") for c in contents)


def test_continuation_turn_no_reinject(ps):
    """After compaction, the continuation reply clears the guard without injecting."""
    _seed(ps)
    _assistant_turn(ps, "working...", _pct(ps, 78))
    _assistant_turn(ps, "[COMPACT_SUMMARY] done", _pct(ps, 78))
    _assistant_turn(ps, "resuming work...", _pct(ps, 78))  # continuation reply
    assert _reminders(ps) == []

    # Guard cleared — next reply injects again if context is still high
    _assistant_turn(ps, "still working", _pct(ps, 78))
    assert len(_reminders(ps)) == 1


def test_refusal_drops_junk_summary(ps):
    """Summary right after a fulfilled compaction is refused and dropped."""
    _seed(ps)
    _assistant_turn(ps, "working...", _pct(ps, 78))
    _assistant_turn(ps, "[COMPACT_SUMMARY] first", _pct(ps, 78))
    n = len(ps.app.message_history.get_messages())

    junk = _assistant_turn(ps, "[COMPACT_SUMMARY] again", _pct(ps, 78))
    msgs = ps.app.message_history.get_messages()
    assert junk not in msgs, "junk summary not dropped"
    assert len(msgs) == n


def test_tool_calls_summary_keeps_assistant(ps):
    """Summary with tool_calls: assistant msg kept intact, normalized to [SUMMARY]."""
    _seed(ps)
    _assistant_turn(ps, "working...", _pct(ps, 78))
    _assistant_turn(ps, "[COMPACT_SUMMARY] summarizing", _pct(ps, 78), tool_calls=True)

    msgs = ps.app.message_history.get_messages()
    last = msgs[-1]
    assert last.get("tool_calls")  # assistant message kept
    assert str(last["content"]).startswith("[SUMMARY]")
    assert ps.app.next_prompt is not None


def test_reminder_strip_regex(ps):
    """_RE_SYSTEM_REMINDER strips appended reminder, keeps question."""
    text = "Q\n\n<system-reminder>\nSYSTEM: x\n</system-reminder>"
    stripped = ps.module._RE_SYSTEM_REMINDER.sub("", text)
    assert stripped == "Q"


def test_nudge_format_tagged(ps):
    """Compaction reminders carry [NUDGE:COMPACTION] (clearable category)."""
    _seed(ps)
    _assistant_turn(ps, "plain reply", _pct(ps, 78))
    assert "[NUDGE:COMPACTION]" in _reminders(ps)[0]["content"]


def test_external_compaction_clears_nudges(ps):
    """after_compaction (compact_strategy/core//compact): COMPACTION nudges
    removed + guard set. Stale-reminder compliance refused, no second
    compaction; next normal reply clears guard without injecting; fresh
    cycle still works."""
    _seed(ps)
    _assistant_turn(ps, "working...", _pct(ps, 78))
    assert len(_reminders(ps)) == 1

    ps.ps.call_hooks("after_compaction")  # external compaction fired
    assert _reminders(ps) == []  # stale reminder gone

    # AI still emits a summary (empty-retry / continuation compliance):
    # refused and dropped, no second compaction.
    n = len(ps.app.message_history.get_messages())
    junk = _assistant_turn(ps, "[COMPACT_SUMMARY] stale compliance", _pct(ps, 78))
    msgs = ps.app.message_history.get_messages()
    assert junk not in msgs
    assert len(msgs) == n
    assert ps.app.message_history.compaction_count == 0

    # Next normal reply: guard cleared, no re-inject.
    _assistant_turn(ps, "resuming", _pct(ps, 78))
    assert _reminders(ps) == []

    # Fresh cycle works.
    _assistant_turn(ps, "more", _pct(ps, 78))
    assert len(_reminders(ps)) == 1
